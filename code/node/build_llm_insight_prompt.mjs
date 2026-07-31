// 기준 제품(anchor)과 추천된 대안 제품(candidate)을 받아서, 웹 클로드/GPT에 그대로
// 붙여넣을 수 있는 "추천 사유 인사이트 문구" 생성 프롬프트를 만들어준다.
//
// - 두 제품의 공통 성분과 data/olive_crwl/ingredient_mapping/ingredient_combo_effect_knowledge.json
//   (승민의 조합-효과 lift 분석 중 확정본)을 대조해서, 실제로 겹치는 조합만 "근거자료"로 프롬프트에 넣는다.
//   겹치는 게 없으면 그 섹션 자체를 비워서 LLM이 없는 시너지를 지어내지 않도록 한다.
// - is_synergy: false로 표시된 항목(예: 나이아신아마이드+아데노신, 단순 인기 조합이지 시너지 아님)은
//   절대 "시너지 근거"로 인용하지 않는다 — 반대로 매칭돼도 무시한다.
//
// 사용법: node code/node/build_llm_insight_prompt.mjs <anchorProductId> <candidateProductId>
import "dotenv/config";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";
import { createClient } from "@supabase/supabase-js";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const KNOWLEDGE_PATH = path.join(
  ROOT,
  "data/olive_crwl/ingredient_mapping/ingredient_combo_effect_knowledge.json"
);
const TOP_N_INGREDIENTS = 15;

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
if (!url || !key) {
  throw new Error("SUPABASE_URL / SUPABASE_(SERVICE_ROLE|ANON)_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, key);

const [, , anchorId, candidateId] = process.argv;
if (!anchorId || !candidateId) {
  console.error("사용법: node code/node/build_llm_insight_prompt.mjs <anchorProductId> <candidateProductId>");
  process.exit(1);
}

function loadKnowledge() {
  return JSON.parse(readFileSync(KNOWLEDGE_PATH, "utf-8"));
}

async function fetchProduct(productId) {
  const { data, error } = await supabase
    .from("products")
    .select("product_id, product_name, category, price_per_10ml, ml_display, ml_estimated_total")
    .eq("product_id", productId)
    .single();
  if (error) throw new Error(`${productId}: ${error.message}`);
  return data;
}

async function fetchTopIngredients(productId) {
  const { data, error } = await supabase
    .from("product_ingredients")
    .select("rank, ingredients(name, effect_tags)")
    .eq("product_id", productId)
    .order("rank")
    .limit(TOP_N_INGREDIENTS);
  if (error) throw new Error(`${productId} 성분 조회 실패: ${error.message}`);
  return data.map((r) => ({ name: r.ingredients.name, effectTags: r.ingredients.effect_tags || [] }));
}

// combo.ingredients의 각 항목은 문자열이거나(단일 성분) 문자열 배열(대체 가능 원료군, 예: 징크옥사이드/티타늄디옥사이드).
// 항목마다 최소 하나가 sharedNames에 있어야 그 조합이 "실제로 겹친다"고 판단.
function comboMatches(combo, sharedNames) {
  return combo.ingredients.every((slot) => {
    const alts = Array.isArray(slot) ? slot : [slot];
    return alts.some((name) => sharedNames.has(name));
  });
}

function formatIngredientLine(list) {
  return list.map((i) => (i.effectTags.length ? `${i.name}[${i.effectTags.join("/")}]` : i.name)).join(", ");
}

function formatVolume(p) {
  return p.ml_display ?? p.ml_estimated_total ?? null;
}

function formatPrice(p) {
  return p.price_per_10ml != null ? `${p.price_per_10ml}원/10ml` : "가격 정보 없음";
}

async function main() {
  const [anchor, candidate] = await Promise.all([fetchProduct(anchorId), fetchProduct(candidateId)]);
  const [anchorIngredients, candidateIngredients] = await Promise.all([
    fetchTopIngredients(anchorId),
    fetchTopIngredients(candidateId),
  ]);

  const anchorNames = new Set(anchorIngredients.map((i) => i.name));
  const candidateNames = new Set(candidateIngredients.map((i) => i.name));
  const sharedNames = new Set([...anchorNames].filter((n) => candidateNames.has(n)));

  const knowledge = loadKnowledge();
  const matchedCombos = knowledge.filter((c) => c.is_synergy && comboMatches(c, sharedNames));

  const knowledgeSection =
    matchedCombos.length === 0
      ? "(공통 성분과 겹치는 검증된 조합 없음 — 이 섹션 무시하고 개별 effect_tag만 근거로 사용할 것)"
      : matchedCombos
          .map(
            (c, i) =>
              `${i + 1}. [${c.confidence}] ${c.ingredients.map((s) => (Array.isArray(s) ? s.join("/") : s)).join(" + ")}\n   ${c.description}`
          )
          .join("\n");

  const prompt = `당신은 스킨케어 성분 전문가입니다. 사용자가 이미 가진 화장품과 성분이 비슷한 "대안 제품"을 추천받았을 때,
왜 이 제품이 합리적인 대안인지 1~2문장으로 설명해야 합니다.

아래 제공된 데이터만 근거로 사용하세요. 제공되지 않은 지식(일반적인 화장품 상식이라도)을 추가하지 마세요.

[기준 제품]
- 이름: ${anchor.product_name}
- 카테고리: ${anchor.category}
- 가격: ${formatPrice(anchor)} / 용량: ${formatVolume(anchor) ?? "정보 없음"}ml
- 핵심 성분(상위 ${TOP_N_INGREDIENTS}개): ${formatIngredientLine(anchorIngredients)}

[추천 제품]
- 이름: ${candidate.product_name}
- 가격: ${formatPrice(candidate)} / 용량: ${formatVolume(candidate) ?? "정보 없음"}ml
- 핵심 성분(상위 ${TOP_N_INGREDIENTS}개): ${formatIngredientLine(candidateIngredients)}
- 공통 성분: ${sharedNames.size ? [...sharedNames].join(", ") : "(상위 성분 기준 겹치는 것 없음)"}

[참고: 검증된 성분 조합-효과 지식 (공통 성분에 실제로 있을 때만 인용하세요)]
${knowledgeSection}

[작성 규칙]
1. 공통 성분과 위 조합-효과 지식이 실제로 겹칠 때만 "시너지 효과"를 언급하세요. 겹치지 않으면 개별 성분의 effect_tag만 언급하세요.
2. confidence가 medium/low인 조합 정보는 "~로 추정됩니다" 같은 단정적이지 않은 표현만 쓰세요.
3. 의학적 효능을 단정하지 마세요("치료", "개선 보장" 금지). "~에 도움을 줄 수 있는 성분 구성" 같은 표현만 사용하세요.
4. "동일 제품"이라고 표현하지 말고 "성분 구성이 유사한 대안"이라고만 표현하세요.
5. 가격/용량 데이터가 있으면 구체적 숫자로 언급하고, 없으면 "가격 정보 없음"이라고 명시하세요(지어내지 마세요).
6. 결과는 1~2문장, 존댓말로.

[출력 형식]
{ "reason": "...", "confidence": "high|medium|low" }`;

  console.log(prompt);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
