// 유사도 검색(match_products)으로 넓게 후보를 뽑은 뒤, 가격/용량 메타데이터를 섞어 최종 순위를 매긴다.
// 1단계(recall): 코사인 유사도로 후보 풀(기본 30개) 확보
// 2단계(rerank): 유사도 + 가격 매력도 + 용량 근접도를 가중합해 재정렬
// 사용법: node code/node/recommend_products.mjs <product_id> [category] [limit] [wSimilarity] [wPrice] [wVolume]
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";
import { fetchRecommendationInputs, rankCandidates } from "./lib/rank_candidates.mjs";

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
if (!url || !key) {
  throw new Error("SUPABASE_URL / SUPABASE_(SERVICE_ROLE|ANON)_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, key);

const [, , anchorId, categoryArg, limitArg, wSimArg, wPriceArg, wVolumeArg] = process.argv;
if (!anchorId) {
  console.error("사용법: node code/node/recommend_products.mjs <product_id> [category] [limit] [wSimilarity] [wPrice] [wVolume]");
  process.exit(1);
}

const limit = limitArg ? Number(limitArg) : 5;
const weights = {
  similarity: wSimArg ? Number(wSimArg) : 0.6,
  price: wPriceArg ? Number(wPriceArg) : 0.25,
  volume: wVolumeArg ? Number(wVolumeArg) : 0.15,
};

async function main() {
  const { anchor, anchorVolume, candidates, volumeById } = await fetchRecommendationInputs(
    supabase,
    anchorId,
    categoryArg
  );
  if (candidates.length === 0) {
    console.log("조건에 맞는 후보가 없습니다.");
    return;
  }

  const ranked = rankCandidates(candidates, volumeById, anchorVolume, weights);

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
