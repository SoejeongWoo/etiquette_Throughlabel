// recommend_products.mjs와 tune_ranking_weights.mjs가 공유하는 recall→rerank 핵심 로직.
// I/O(Supabase 조회)는 fetchRecommendationInputs로 한 번만 하고, rankCandidates는 순수 계산만 담당한다 —
// 그래야 튜닝 스크립트가 anchor당 한 번만 조회하고 가중치 조합별로는 재계산만 하면 된다.

const CANDIDATE_POOL = 30;

function parseEmbedding(value) {
  return typeof value === "string" ? JSON.parse(value) : value;
}

// anchor 조회 + match_products(recall) + 후보군 용량 조회까지, 가중치와 무관한 부분을 한 번에 수행.
export async function fetchRecommendationInputs(supabase, anchorId, categoryArg) {
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

  let volumeById = new Map();
  if (candidates.length > 0) {
    const ids = candidates.map((c) => c.product_id);
    const { data: volumeRows, error: volError } = await supabase
      .from("products")
      .select("product_id, ml_display, ml_estimated_total")
      .in("product_id", ids);
    if (volError) throw new Error(volError.message);
    volumeById = new Map(volumeRows.map((r) => [r.product_id, r.ml_display ?? r.ml_estimated_total ?? null]));
  }

  return { anchor, anchorVolume, candidates, volumeById };
}

// 후보군 "안에서" min-max 정규화. null/undefined는 그대로 null 반환(나중에 중립값 0.5로 처리).
export function minMaxNormalize(values) {
  const finite = values.filter((v) => v !== null && v !== undefined && !Number.isNaN(v));
  if (finite.length === 0) return () => null;
  const min = Math.min(...finite);
  const max = Math.max(...finite);
  if (max === min) return (v) => (v === null || v === undefined ? null : 0.5);
  return (v) => (v === null || v === undefined ? null : (v - min) / (max - min));
}

// candidates: match_products RPC 결과 배열 (product_id, product_name, price_per_10ml, similarity 등 포함)
// volumeById: Map<product_id, volume_ml|null>
// anchorVolume: 기준 제품 용량(ml) 또는 null
// weights: { similarity, price, volume } (합 1 권장, 강제하지는 않음)
export function rankCandidates(candidates, volumeById, anchorVolume, weights) {
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
  return ranked;
}
