"""ingredient_combination_effect_mapping.xlsx의 '조합_효과_매핑(핵심)' 시트를
code/node/build_llm_insight_prompt.mjs가 읽을 수 있는 JSON으로 변환한다.

이 시트가 갱신될 때마다(승민이 조합-효과 분석을 다시 돌릴 때) 재실행해서
data/olive_crwl/ingredient_mapping/ingredient_combo_effect_knowledge.json을 갱신해야 한다.
"""

import json
import re
from pathlib import Path

import openpyxl

PAREN_NOTE = re.compile(r"\s*\([^)]*\)\s*")

ROOT = Path(__file__).resolve().parent.parent.parent
XLSX_PATH = ROOT / "data/olive_crwl/ingredient_mapping/xlsx/ingredient_combination_effect_mapping.xlsx"
OUT_PATH = ROOT / "data/olive_crwl/ingredient_mapping/ingredient_combo_effect_knowledge.json"


def main():
    wb = openpyxl.load_workbook(XLSX_PATH, data_only=True)
    ws = wb["조합_효과_매핑(핵심)"]
    rows = list(ws.iter_rows(values_only=True))
    header, data_rows = rows[0], rows[1:]
    assert header == ("조합", "조합크기", "등장상품수", "lift", "조합유형", "효과설명", "근거", "confidence")

    combos = []
    for combo, size, count, lift, combo_type, description, evidence, confidence in data_rows:
        # "나이아신아마이드 + 아데노신 (+글리세린+판테놀+토코페롤 등 고빈도 성분군)" 처럼
        # 괄호 안에 부가 설명이 "+"로 이어붙어 있는 경우가 있어, 괄호 내용부터 제거하고 분리한다.
        cleaned = PAREN_NOTE.sub(" ", str(combo))
        ingredients = [s.strip() for s in cleaned.split("+") if s.strip()]
        # "징크옥사이드/티타늄디옥사이드"처럼 "/"로 묶인 항목은 대체 가능한(둘 중 하나면 충족) 원료군이므로
        # 매칭 스크립트가 alt 목록으로 처리할 수 있게 리스트 형태로 남겨둔다.
        ingredients = [s.split("/") if "/" in s else s for s in ingredients]
        combos.append({
            "ingredients": ingredients,
            "combo_size": size,
            "product_count": count,
            "lift": lift,
            "combo_type": combo_type,
            "description": description,
            "evidence": evidence,
            "confidence": confidence,
            # "단순 동반 인기(디자인된 궁합 아님)" 같은 행은 성분이 겹쳐도 시너지로 인용하면 안 됨 —
            # 오히려 "이건 우연일 뿐 시너지 아님"을 프롬프트에 알려주기 위한 반례 데이터.
            "is_synergy": "디자인된 궁합" not in str(combo_type) and "동반 인기" not in str(combo_type),
        })

    OUT_PATH.write_text(json.dumps(combos, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(combos)}개 조합 저장: {OUT_PATH}")


if __name__ == "__main__":
    main()
