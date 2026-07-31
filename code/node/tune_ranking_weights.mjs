// recommend_products.mjs의 가중치(유사도/가격/용량)를 여러 조합으로 바꿔가며,
// 같은 anchor 제품에서 top-5가 어떻게 달라지는지 한 번에 비교해서 보여준다.
//
// 아직 실사용 클릭/구매 데이터가 없어서 "정답 랭킹"을 학습할 수는 없다 — 대신 대표 anchor
// 몇 개로 여러 가중치 후보안을 정성 비교하고, 가중치를 살짝만 바꿔도 1위가 계속 바뀌는(불안정한)
// 조합은 피하는 식으로 튜닝한다.
//
// 사용법: node code/node/tune_ranking_weights.mjs [anchorId1 anchorId2 ...]
// (anchor를 안 주면 기본 대표 세트: 크림/로션/선크림 각 1개)
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";
import { fetchRecommendationInputs, rankCandidates } from "./lib/rank_candidates.mjs";

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
if (!url || !key) {
  throw new Error("SUPABASE_URL / SUPABASE_(SERVICE_ROLE|ANON)_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, key);

const DEFAULT_ANCHORS = ["pi_cream_A000000236828", "pi_lotion_A000000214459", "sunCream_03"];

// 가중치 후보안. 필요하면 여기 목록만 바꿔서 다른 조합을 시험해볼 수 있다.
const WEIGHT_PRESETS = [
  { label: "유사도만(baseline)", similarity: 1.0, price: 0.0, volume: 0.0 },
  { label: "현재 기본값", similarity: 0.6, price: 0.25, volume: 0.15 },
  { label: "유사도 강조", similarity: 0.7, price: 0.2, volume: 0.1 },
  { label: "가격 강조", similarity: 0.5, price: 0.35, volume: 0.15 },
  { label: "용량 강조", similarity: 0.5, price: 0.25, volume: 0.25 },
  { label: "가격 매우 강조", similarity: 0.4, price: 0.4, volume: 0.2 },
];

const anchorIds = process.argv.slice(2);
const anchors = anchorIds.length > 0 ? anchorIds : DEFAULT_ANCHORS;

async function tuneOneAnchor(anchorId) {
  const { anchor, anchorVolume, candidates, volumeById } = await fetchRecommendationInputs(supabase, anchorId, null);
  if (candidates.length === 0) {
    console.log(`\n[${anchorId}] 후보 없음, 스킵`);
    return;
  }

  console.log(`\n=== 기준 제품: ${anchor.product_name} (${anchor.category}, ${anchorVolume ?? "용량 미상"}ml) ===`);

  const top1PerPreset = [];
  for (const preset of WEIGHT_PRESETS) {
    const ranked = rankCandidates(candidates, volumeById, anchorVolume, preset);
    const top3 = ranked.slice(0, 3);
    top1PerPreset.push(top3[0]?.product_id ?? null);
    console.log(
      `\n[${preset.label}] 유사도${preset.similarity}/가격${preset.price}/용량${preset.volume}`
    );
    console.table(
      top3.map((r) => ({
        product_id: r.product_id,
        product_name: r.product_name,
        similarity: r.similarity.toFixed(4),
        price_per_10ml: r.price_per_10ml,
        final_score: r.final_score.toFixed(4),
      }))
    );
  }

  const distinctWinners = new Set(top1PerPreset.filter(Boolean));
  console.log(
    `[요약] 가중치 조합 ${WEIGHT_PRESETS.length}개 중 1위가 바뀐 횟수: ${distinctWinners.size}가지 서로 다른 1위` +
      (distinctWinners.size === 1
        ? " → 안정적(가중치를 바꿔도 1위 그대로)"
        : distinctWinners.size >= WEIGHT_PRESETS.length - 1
        ? " → 불안정(거의 조합마다 1위가 바뀜, 이 anchor는 가중치에 민감함)"
        : "")
  );
}

async function main() {
  for (const anchorId of anchors) {
    await tuneOneAnchor(anchorId);
  }
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
