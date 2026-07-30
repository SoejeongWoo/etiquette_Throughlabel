// 유사도 검색(match_products)으로 넓게 후보를 뽑은 뒤, 가격/용량 메타데이터를 섞어 최종 순위를 매긴다.
// 1단계(recall): 코사인 유사도로 후보 풀(기본 30개) 확보
// 2단계(rerank): 유사도 + 가격 매력도 + 용량 근접도를 가중합해 재정렬
// 사용법: node scripts/recommend_products.mjs <product_id> [category] [limit] [wSimilarity] [wPrice] [wVolume]
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
if (!url || !key) {
  throw new Error("SUPABASE_URL / SUPABASE_(SERVICE_ROLE|ANON)_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, key);

const CANDIDATE_POOL = 30;

const [, , anchorId, categoryArg, limitArg, wSimArg, wPriceArg, wVolumeArg] = process.argv;
if (!anchorId) {
  console.error("사용법: node scripts/recommend_products.mjs <product_id> [category] [limit] [wSimilarity] [wPrice] [wVolume]");
  process.exit(1);
}

const limit = limitArg ? Number(limitArg) : 5;
const weights = {
  similarity: wSimArg ? Number(wSimArg) : 0.6,
  price: wPriceArg ? Number(wPriceArg) : 0.25,
  volume: wVolumeArg ? Number(wVolumeArg) : 0.15,
};

function parseEmbedding(value) {
  return typeof value === "string" ? JSON.parse(value) : value;
}

// 후보군 내에서 min-max 정규화. null/undefined는 그대로 null 반환(나중에 중립값 0.5로 처리).
function minMaxNormalize(values) {
  const finite = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (finite.length === 0) return () => null;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  if (max === min) return (v) => (v === null || v === undefined ? null : 0.5);
  return (v) => (v === null || v === undefined ? null : (v - min) / (max - min));
}

async function main() {
  const { data: anchor, error: anchorError } = await supabase
    .from("products")
    .select("product_id, product_name, category, embedding, ml_display, ml_estimated_total")
    .eq("product_id", anchorId)
    .single();
  if (anchorError) throw new Error(anchorError.message);
  if (!anchor.embedding) throw new Error("이 제품은 아직 임베딩이 없습니다 (load_embeddings_to_supabase.mjs 먼저 실행).");
  const anchorVolume = anchor.ml_display ?? anchor.ml_estimated_total ?? null;

  const { data: candidates, error } = await supabase.rpc("match_products", {
    query_embedding: parseEmbedding(anchor.embedding),
    match_category: categoryArg || anchor.category,
    match_count: CANDIDATE_POOL,
    exclude_product_id: anchorId,
  });
  if (error) throw new Error(error.message);
  if (candidates.length === 0) {
    console.log("조건에 맞는 후보가 없습니다.");
    return;
  }

  // match_products는 용량 컬럼을 안 주므로 후보군만 별도 조회.
  const ids = candidates.map((c) => c.product_id);
  const { data: volumeRows, error: volError } = await supabase
    .from("products")
    .select("product_id, ml_display, ml_estimated_total")
    .in("product_id", ids);
  if (volError) throw new Error(volError.message);
  const volumeById = new Map(volumeRows.map((r) => [r.product_id, r.ml_display ?? r.ml_estimated_total ?? null]));

  const priceNorm = minMaxNormalize(candidates.map((c) => c.price_per_10ml));
  const volDiffs = candidates.map((c) => {
    const volume = volumeById.get(c.product_id) ?? null;
    return volume !== null && anchorVolume !== null ? Math.abs(volume - anchorVolume) : null;
  });
  const volDiffNorm = minMaxNormalize(volDiffs);

  const ranked = candidates.map((c, i) => {
    const priceNormVal = priceNorm(c.price_per_10ml);
    const priceScore = priceNormVal === null ? 0.5 : 1 - priceNormVal; // 저렴할수록 1에 가까움
    const volDiffNormVal = volDiffNorm(volDiffs[i]);
    const volumeScore = volDiffNormVal === null ? 0.5 : 1 - volDiffNormVal; // 용량 차이 작을수록 1에 가까움

    const finalScore =
      weights.similarity * c.similarity + weights.price * priceScore + weights.volume * volumeScore;

    return {
      ...c,
      volume_ml: volumeById.get(c.product_id) ?? null,
      price_score: priceScore,
      volume_score: volumeScore,
      final_score: finalScore,
    };
  });

  ranked.sort((a, b) => b.final_score - a.final_score);

  console.log(`기준 제품: ${anchor.product_name} (${anchor.category}, ${anchorVolume ?? "용량 미상"}ml)`);
  console.log(`가중치: 유사도 ${weights.similarity} / 가격매력도 ${weights.price} / 용량근접도 ${weights.volume}`);
  console.table(
    ranked.slice(0, limit).map((r) => ({
      product_id: r.product_id,
      product_name: r.product_name,
      similarity: r.similarity.toFixed(4),
      price_per_10ml: r.price_per_10ml,
      volume_ml: r.volume_ml,
      price_score: r.price_score.toFixed(3),
      volume_score: r.volume_score.toFixed(3),
      final_score: r.final_score.toFixed(4),
    }))
  );
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
