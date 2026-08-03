# -*- coding: utf-8 -*-
"""성분 간 상호작용 지식베이스 생성.

입력은 data/olive_crwl/ingredient_mapping/xlsx/ingredient_effect_mapping.xlsx /
ingredient_combination_effect_mapping.xlsx로 지정됐으나, 두 파일 모두 최근 재분류
(fea36a7/b4d1093)와 suncream 전체크롤링 반영 전 시점이라 stale하다(예: 아이비고드열매
추출물이 아직 low, 시트로넬올이 아직 미분류, lift 데이터는 예전 소규모 표본 기준).
대신 최신 소스를 직접 사용한다:
  - 성분 분류/confidence: ingredient_mapping/csv/ingredient_effect_mapping_성분매핑(Sonnet5).csv
  - 상품-성분 데이터: price_ingredient_all/csv/*.csv (suncream 포함, normalize_ingredients.py 파싱 재사용)

INTERACTIONS는 통계적 동시출현이 아니라 화장품학적 지식(성분의 pH 안정성, 알려진
배합 관행, 문헌상 상호작용)에 근거해 사람이 직접 채운 목록이다. lift는 "얼마나 자주
같이 쓰이는지"의 참고 지표일 뿐 conflict/synergy 판정 근거로 쓰지 않았다(과제 규칙 3).
확실하지 않은 조합은 행을 만들지 않았고(과제 규칙 2), 만든 행 중에서도 근거가
약한 것은 confidence=low로 표기했다.
"""
import sys
from pathlib import Path
from collections import Counter

sys.stdout.reconfigure(encoding="utf-8")  # Windows cp949 콘솔에서 —, · 등 출력 시 깨지는 문제 방지

REPO = Path(r"c:/Users/82106/Desktop/멋사부트캠프/skincare/olive_crwl")
sys.path.insert(0, str(REPO / "code" / "python"))
import normalize_ingredients as norm
import pandas as pd

MAPPING_CSV = REPO / "data/olive_crwl/ingredient_mapping/csv/ingredient_effect_mapping_성분매핑(Sonnet5).csv"
ALL_DIR = REPO / "data/olive_crwl/price_ingredient_all/csv"
OUT_CSV = REPO / "data/olive_crwl/ingredient_mapping/csv/ingredient_interaction.csv"

TOP_N = 60  # 대상 액티브/UV필터 성분 수 (빈도 상위)

PRICE_FILES = {
    "mistOil": "mistOil_price_ingredient_all.csv",
    "lotion": "lotion_price_ingredient_all.csv",
    "skinToner": "skinToner_price_ingredient_all.csv",
    "cream": "cream_price_ingredient_all.csv",
    "essenceSerumAmpoule": "essenceSerumAmpoule_price_ingredient_all.csv",
    "suncream": "suncream_price_ingredient_all.csv",
}


def compute_true_frequency():
    """가격표 원본에서 실제 빈도를 다시 계산한다(매핑 CSV의 '빈도(상품수)' 컬럼은
    예전 소규모 표본 기준이라 신뢰하지 않는다 — 이미 재분류 작업에서 확인된 이슈)."""
    norm.STANDARD_NAME_MAP = norm.load_standard_name_map()
    freq = Counter()
    for fname in PRICE_FILES.values():
        df = pd.read_csv(ALL_DIR / fname)
        for raw in df.get("ingredient", []):
            for name in set(norm.parse_ingredient_list(raw)):
                freq[name] += 1
    return freq


def top_active_ingredients(n=TOP_N):
    freq = compute_true_frequency()
    df = pd.read_csv(MAPPING_CSV)
    active = df[df["성분_유형"].isin(["액티브", "UV필터"])].copy()
    active["true_freq"] = active["ingredient"].map(lambda x: freq.get(x, 0))
    active = active.sort_values("true_freq", ascending=False)
    return active.head(n)["ingredient"].tolist()


# ===== 상호작용 지식베이스 (사람이 직접 작성, 화장품학적 근거 기반) =====
# 컬럼: ingredient_a, ingredient_b, interaction_type, mechanism, severity, layering_note, confidence, evidence
INTERACTIONS = [
    dict(
        ingredient_a="아스코빅애씨드", ingredient_b="나이아신아마이드",
        interaction_type="neutral",
        mechanism=(
            "과거 저온 시험관 실험(1960년대)에서 나이아신아마이드가 산성 조건의 아스코빅애씨드와 "
            "반응해 나이아신(홍조 유발 가능 물질)을 생성한다는 보고가 있었으나, 현재 상용 제형의 "
            "pH·농도·상온 조건에서는 유의미한 반응이 일어나지 않는다는 것이 현재 화장품학계의 통설이다. "
            "널리 퍼진 '병용 금기' 속설은 최신 통설과 다르다."
        ),
        severity="", layering_note="",
        confidence="medium", evidence="공개 처방 관행",
    ),
    dict(
        ingredient_a="아스코빅애씨드", ingredient_b="카퍼트라이펩타이드-1",
        interaction_type="conflict",
        mechanism="구리 이온이 아스코빅애씨드의 산화를 촉진해 두 성분의 안정성과 효능이 저하될 수 있음",
        severity=2, layering_note="아침/저녁으로 시간차를 두고 사용 권장",
        confidence="medium", evidence="원료사 기술자료",
    ),
    dict(
        ingredient_a="소듐하이알루로네이트", ingredient_b="하이드롤라이즈드하이알루로닉애씨드",
        interaction_type="synergy",
        mechanism="분자량이 다른 하이알루론산 유도체를 병용하면 서로 다른 피부 깊이(고분자=표면, 저분자=각질층 하부)에서 보습막을 형성해 보습 효과가 중첩됨",
        severity="", layering_note="",
        confidence="high", evidence="원료사 기술자료",
    ),
    dict(
        ingredient_a="세라마이드엔피", ingredient_b="콜레스테롤",
        interaction_type="synergy",
        mechanism="세라마이드와 콜레스테롤은 각질층 라멜라 지질구조를 이루는 핵심 지질로, 함께 배합될 때 피부장벽 재구성 효과가 단독 사용보다 큰 것으로 알려져 있음",
        severity="", layering_note="",
        confidence="high", evidence="원료사 기술자료",
    ),
    dict(
        ingredient_a="에칠헥실트리아존", ingredient_b="비스-에칠헥실옥시페놀메톡시페닐트리아진",
        interaction_type="synergy",
        mechanism="두 유기 자외선차단성분의 흡수 파장대가 서로 보완적이어서 병용 시 광범위(UVA/UVB) 차단 효과가 높아짐",
        severity="", layering_note="",
        confidence="high", evidence="공개 처방 관행",
    ),
    dict(
        ingredient_a="티타늄디옥사이드", ingredient_b="에칠헥실트리아존",
        interaction_type="synergy",
        mechanism="무기 자외선차단성분(산란 방식)과 유기 자외선차단성분(흡수 방식)을 병용하는 하이브리드 방식은 차단 스펙트럼을 넓히는 표준적인 제형 전략임",
        severity="", layering_note="",
        confidence="high", evidence="공개 처방 관행",
    ),
    dict(
        ingredient_a="다이포타슘글리시리제이트", ingredient_b="아스코빅애씨드",
        interaction_type="conflict",
        mechanism=(
            "다이포타슘글리시리제이트(감초 추출물의 염 형태)는 중성~약알칼리 조건에서, 아스코빅애씨드는 "
            "산성(pH 약 3.5) 조건에서 안정적이어서 동일 제형 내 공존 시 안정성이 상충할 가능성이 있음 — "
            "실제 병용 안정성에 대한 구체적 검증 자료는 확인 필요"
        ),
        severity=1, layering_note="동일 제품보다는 별도 스텝으로 사용 고려",
        confidence="low", evidence="추정",
    ),
    dict(
        ingredient_a="글루타티온", ingredient_b="아스코빅애씨드",
        interaction_type="synergy",
        mechanism="비타민C와 글루타티온은 항산화 네트워크에서 서로의 산화된 형태를 환원시켜 재생하는 상호보완적 관계로 알려져 있으나, 국소도포 화장품 맥락에서의 실증 자료는 제한적임",
        severity="", layering_note="",
        confidence="medium", evidence="추정",
    ),
    dict(
        ingredient_a="병풀추출물", ingredient_b="마데카소사이드",
        interaction_type="neutral",
        mechanism="병풀추출물과 마데카소사이드는 같은 식물(센텔라아시아티카) 유래의 활성 분획들로, 병용은 흔하지만 이는 두 성분이 만드는 독립적 시너지라기보다 원료 자체의 중복 표기에 가까움",
        severity="", layering_note="",
        confidence="medium", evidence="원료사 기술자료",
    ),
    dict(
        ingredient_a="소듐하이알루로네이트크로스폴리머", ingredient_b="스쿠알란",
        interaction_type="synergy",
        mechanism="가교 히알루론산(습윤제)이 형성하는 보습 필름 위에 스쿠알란(폐색제)이 유막을 더해 수분 손실을 이중으로 방지하는, 습윤제+폐색제 병용은 보습 제형의 기본 원칙임",
        severity="", layering_note="",
        confidence="high", evidence="공개 처방 관행",
    ),
]

COLUMNS = ["ingredient_a", "ingredient_b", "interaction_type", "mechanism",
           "severity", "layering_note", "confidence", "evidence"]


def main(sample_only=None, dry_run=True):
    """dry_run=True면 검증만 하고 파일을 쓰지 않는다(기본값). 승인 후 dry_run=False로 실행."""
    top60 = top_active_ingredients(TOP_N)
    top60_set = set(top60)

    rows = INTERACTIONS[:sample_only] if sample_only else INTERACTIONS
    not_in_top60 = [
        (r["ingredient_a"], r["ingredient_b"]) for r in rows
        if r["ingredient_a"] not in top60_set or r["ingredient_b"] not in top60_set
    ]
    if not_in_top60:
        print(f"경고: top-{TOP_N}에 없는 성분이 포함된 행: {not_in_top60}")

    df = pd.DataFrame(rows)[COLUMNS]
    print(f"{'[SAMPLE]' if sample_only else '[FULL]'} 행 수: {len(df)}")
    print(df.to_string())

    if dry_run:
        print("\n(dry_run=True: 파일 저장 안 함. 승인 후 main(dry_run=False)로 재실행)")
    else:
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
        print(f"저장 완료: {OUT_CSV}")

    return df


if __name__ == "__main__":
    main(dry_run=True)
