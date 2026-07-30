"""products.csv + 8개 카테고리 price_ingredient CSV의 성분 텍스트를 정규화해서
data/supabase/products.csv, data/supabase/ingredients.csv, data/supabase/product_ingredients.csv로 만든다.
(Supabase 적재는 scripts/node/load_to_supabase.mjs가 이 세 파일을 읽어서 수행)

정규화 규칙 (raw ingredient 텍스트의 알려진 문제들):
1. 여러 줄(\\r\\n)로 된 텍스트는 콤마가 가장 많은 줄만 실제 성분 리스트로 취급하고
   나머지(상품명, 각주 등)는 버린다.
2. "전성분 :" 마커 앞의 마케팅 문구, 맨 앞 "[...]" 태그를 제거한다.
3. "1,2-헥산다이올" "2,3-부탄다이올" 처럼 이름 안에 콤마가 들어간 성분이 있어서
   콤마로만 자르면 "1"/"2-헥산다이올"처럼 깨진다. 분리 후 1~2자리 숫자만 남은 토큰은
   다음 토큰과 다시 합친다.
4. 각 토큰의 "(29,049ppm)" "5%" 같은 함량 표기를 제거한다.
5. 내부에 낀 공백(예: "소듐하이알루로 네이트")은 전부 제거한다 — 이 데이터셋의 성분명은
   공백을 포함하지 않는다.
6. 마지막 토큰에 "iln48715/iln48715" 같은 크롤링 잔재 코드가 붙는 경우가 있어
   (소문자 2자 이상 + 숫자 3자리 이상 패턴) 마지막 토큰에서만 제거한다.

기존 공통_ingredient/차별화_ingredient 컬럼은 같은 카테고리 안에서 상품마다 값이
들쭉날쭉해(예: cream 카테고리에서 "정제수, 글리세린" / "정제수" / "글리세린, 정제수"가
섞여 나옴 — 둘 다 원문에 존재하는데도) 신뢰하지 않고, 파싱된 성분 리스트를 기준으로
카테고리별 공통 여부를 다시 계산한다.
"""

import re
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent.parent
OUT_DIR = ROOT / "data" / "supabase"
RAW_DIR = ROOT / "data" / "olive_crwl"
# csv/xlsx로 먼저 나뉘고, 그 안에서 다시 용도별(50개 근사표본/전체크롤링/원본크롤링/성분매핑)로 나뉘어 있다.
ALL_DIR = RAW_DIR / "price_ingredient_all" / "csv"
FIFTY_DIR = RAW_DIR / "price_ingredient_50" / "csv"
PRODUCTS_DIR = RAW_DIR / "products_reviews" / "csv"
MAPPING_DIR = RAW_DIR / "ingredient_mapping" / "csv"

# 올리브영 스킨케어 전체 크롤링(dispCatNo 5개 통짜 카테고리, "_all")이 끝난 카테고리는
# 베스트 50개 근사 표본("_50")보다 그걸 우선 사용한다. essence/serum/ampoule은 애초에
# 올리브영에 독립 카테고리가 없어 "에센스/세럼/앰플" 통합 목록에서 키워드로 골라낸
# 근사 데이터였으므로, 통합 전체 크롤링(essenceSerumAmpoule_all)이 준비되면 그 하나로
# 대체하고 세 개의 근사 카테고리는 쓰지 않는다.
PRICE_SOURCES = [
    ("cream", "cream_price_ingredient_all.csv", "cream_price_ingredient_50.csv"),
    ("toner", "skinToner_price_ingredient_all.csv", "toner_price_ingredient_50.csv"),
    ("suncream", None, "suncream_price_ingredient_50.csv"),
    ("lotion", "lotion_price_ingredient_all.csv", "lotion_price_ingredient_50.csv"),
    ("mist", "mistOil_price_ingredient_all.csv", "mist_price_ingredient_50.csv"),
]
ESSENCE_SERUM_AMPOULE_ALL = "essenceSerumAmpoule_price_ingredient_all.csv"
ESSENCE_SERUM_AMPOULE_FALLBACK = [
    ("essence", "essence_price_ingredient_50.csv"),
    ("serum", "serum_price_ingredient_50.csv"),
    ("ampoule", "ampoule_price_ingredient_50.csv"),
]


def resolve_price_sources() -> list[tuple[str, Path]]:
    """(category_label, csv_path) 목록. "_all"이 있으면 그걸, 없으면 "_50" 근사치를 쓴다."""
    resolved = []
    for label, all_name, fallback_name in PRICE_SOURCES:
        all_path = ALL_DIR / all_name if all_name else None
        if all_path and all_path.exists():
            resolved.append((label, all_path))
        else:
            resolved.append((label, FIFTY_DIR / fallback_name))

    esa_path = ALL_DIR / ESSENCE_SERUM_AMPOULE_ALL
    if esa_path.exists():
        resolved.append(("essenceSerumAmpoule", esa_path))
    else:
        for label, fallback_name in ESSENCE_SERUM_AMPOULE_FALLBACK:
            resolved.append((label, FIFTY_DIR / fallback_name))
    return resolved

LEADING_MARKER = re.compile(r"^.*?전\s*성분\s*[:：]\s*", re.S)
LEADING_BRACKET = re.compile(r"^\s*\[[^\]]{0,40}\]\s*")
QUANTITY = re.compile(r"\(?\s*[\d,.]+\s*(?:%|ppm|ppb|mcg|mg|ml|iu\s*/?\s*g)\s*\)?", re.I)
CI_CODE = re.compile(r"\(\s*CI\s*\d+\s*\)", re.I)  # 색소의 Color Index 표기, 표준명엔 없음
TRAILING_JUNK = re.compile(r"[a-z]{2,}\d{3,}[a-zA-Z0-9/]*$")
EDGE_PUNCT = re.compile(r"^[^\w가-힣()]+|[^\w가-힣()]+$")
LONE_LOCANT = re.compile(r"^\d{1,2}$")


def join_wrapped_lines(text: str) -> str:
    """줄바꿈은 구분자가 아니라 화면 폭에 맞춘 줄바꿈일 뿐이라, 그대로 이어붙인다.
    (이전 버전은 '콤마가 가장 많은 한 줄만 채택'했는데, 전성분표 전체가 여러 줄에
    걸쳐 있는 상품에서는 이 방식이 뒷부분 성분들을 통째로 날려버리는 버그였다.)
    """
    text = text.replace("@", ",")  # 일부 행에서 리스트 구분자로 "@"가 잘못 쓰인 경우 복구
    text = text.replace("•", "-")  # 스캔/스크래핑 과정에서 "-"가 "•"로 깨진 경우 복구
    return text.replace("\r\n", "").replace("\n", "")


def strip_prefix(segment: str) -> str:
    if "전성분" in segment or "전 성분" in segment:
        segment = LEADING_MARKER.sub("", segment)
    return LEADING_BRACKET.sub("", segment)


def repair_comma_split(raw_tokens: list[str]) -> list[str]:
    """콤마 분리로 깨진 토큰을 복구한다.
    - '1,2-헥산다이올'처럼 이름 안에 콤마가 들어간 경우 (앞 토큰이 1~2자리 숫자만 남음)
    - '판테놀(5,000ppm)'처럼 함량 표기 안의 콤마 (여는 괄호만 있고 닫는 괄호가 없는 토큰)
    두 경우 모두 다음 토큰과 다시 합쳐서 복구한다.
    """
    repaired = []
    i = 0
    n = len(raw_tokens)
    while i < n:
        tok = raw_tokens[i]
        while i + 1 < n and (
            tok.count("(") > tok.count(")") or LONE_LOCANT.fullmatch(tok.strip())
        ):
            i += 1
            tok = f"{tok},{raw_tokens[i]}"
        repaired.append(tok)
        i += 1
    return repaired


def clean_token(token: str, is_last: bool) -> str:
    t = QUANTITY.sub("", token)
    t = CI_CODE.sub("", t)
    if is_last:
        t = TRAILING_JUNK.sub("", t)
    t = re.sub(r"\s+", "", t)
    t = EDGE_PUNCT.sub("", t)
    return t


def load_standard_name_map() -> dict[str, str]:
    """식약처 성분사전 '표준화명칭목록'(별첨1, data/supabase/standard_ingredient_names.csv 로 추출됨)에서
    구명칭(alias) -> 표준 성분명 매핑을 만든다. 표준명 자기 자신도 항등 매핑으로 포함.
    """
    path = OUT_DIR / "standard_ingredient_names.csv"
    if not path.exists():
        return {}
    df = pd.read_csv(path)
    df = df[df["ingredient_code"].astype(str).str.fullmatch(r"\d+")]
    mapping: dict[str, str] = {}
    for _, r in df.iterrows():
        std_raw = r.get("standard_name_kr")
        if not isinstance(std_raw, str) or not std_raw.strip():
            continue
        std = clean_token(std_raw, is_last=True)
        if not std:
            continue
        mapping[std] = std
        alias_raw = r.get("alias_kr")
        if isinstance(alias_raw, str) and alias_raw.strip():
            for a in alias_raw.split("|"):
                a = clean_token(a, is_last=True)
                if a:
                    mapping[a] = std
    return mapping


STANDARD_NAME_MAP: dict[str, str] = {}


def parse_ingredient_list(raw) -> list[str]:
    if not isinstance(raw, str) or not raw.strip():
        return []
    segment = strip_prefix(join_wrapped_lines(raw))
    raw_tokens = repair_comma_split(segment.split(","))
    n = len(raw_tokens)
    cleaned = []
    for i, tok in enumerate(raw_tokens):
        c = clean_token(tok, is_last=(i == n - 1))
        if c and not c.isdigit():
            cleaned.append(STANDARD_NAME_MAP.get(c, c))
    return cleaned


def load_effect_mapping() -> pd.DataFrame:
    """ingredient_effect_mapping_성분매핑(Sonnet5).csv(2,454개 원본 고유 성분 목록)를 정규화한다.

    이 목록 자체도 노이즈가 있다: "1,2-헥산다이올*" / "1,2 -헥산다이올" 같은 표기 흔들림이
    정규화 후 같은 이름으로 합쳐지고(의도된 동작), "2-헥산다이올@정제수@판테놀@..." 처럼
    성분 리스트 전체가 한 행에 잘못 들어간 깨진 행도 섞여 있다(제외).
    같은 이름으로 합쳐진 경우 빈도(상품수)가 가장 큰 행의 태그 정보를 대표값으로 쓴다.
    """
    df = pd.read_csv(MAPPING_DIR / "ingredient_effect_mapping_성분매핑(Sonnet5).csv")
    df = df[~df["ingredient"].astype(str).str.contains("@", regex=False)]
    df["name"] = df["ingredient"].map(
        lambda s: STANDARD_NAME_MAP.get(c := clean_token(str(s), is_last=True), c)
    )
    df = df[df["name"] != ""]
    df = df.sort_values("빈도(상품수)", ascending=False).drop_duplicates("name", keep="first")
    return df.set_index("name")[
        ["빈도(상품수)", "성분_유형", "ingredient_tag", "label_confidence", "검수필요"]
    ]


def build_products_dataset() -> tuple[pd.DataFrame, dict]:
    """returns (products_df, {product_id: [ingredient_name, ...] in order})"""
    rows = []
    product_ingredients: dict[str, list[str]] = {}

    products_csv = pd.read_csv(PRODUCTS_DIR / "products.csv")
    for _, r in products_csv.iterrows():
        pid = str(r["product_id"])
        ing_list = parse_ingredient_list(r.get("ingredient"))
        product_ingredients[pid] = ing_list
        rows.append({
            "product_id": pid,
            "category": r["category"],
            "product_name": r["product_name"],
            "brand_name": r.get("brand_name"),
            "manufacturer": r.get("manufacturer"),
            "brand": r.get("brand"),
            "manufacturer_confidence": r.get("manufacturer_confidence"),
            "goods_no": r.get("goods_no") if pd.notna(r.get("goods_no")) else None,
            "data_source": "olive_crwl_products",
            "ml_display": None,
            "ml_estimated_total": None,
            "volume_unit": None,
            "price_regular": None,
            "price_sale": None,
            "price_per_10ml": None,
            "raw_ingredient_text": r.get("ingredient"),
        })

    for cat, csv_path in resolve_price_sources():
        df = pd.read_csv(csv_path)
        for idx, r in df.iterrows():
            goods_no = r.get("goods_no")
            pid = f"pi_{cat}_{goods_no}" if pd.notna(goods_no) else f"pi_{cat}_{idx:03d}"
            ing_list = parse_ingredient_list(r.get("ingredient"))
            product_ingredients[pid] = ing_list
            rows.append({
                "product_id": pid,
                "category": cat,
                "product_name": r["product_name"],
                "brand_name": r.get("brand_name"),
                "manufacturer": None,
                "brand": None,
                "manufacturer_confidence": None,
                "goods_no": goods_no if pd.notna(goods_no) else None,
                "data_source": "olive_crwl_price_ingredient",
                "ml_display": r.get("ml_표시용량"),
                "ml_estimated_total": r.get("ml_추정총용량"),
                "volume_unit": r.get("용량_단위"),
                "price_regular": r.get("price_regular"),
                "price_sale": r.get("price_sale"),
                "price_per_10ml": r.get("price_per_10ml"),
                "raw_ingredient_text": r.get("ingredient"),
            })

    return pd.DataFrame(rows), product_ingredients


def compute_common_flags(products_df: pd.DataFrame, product_ingredients: dict) -> dict:
    """category별로, 성분 데이터가 있는 상품 중 n-1개 이상에 등장하면 공통으로 표시."""
    is_common: dict[tuple[str, str], bool] = {}
    for category, group in products_df.groupby("category"):
        pids_with_data = [pid for pid in group["product_id"] if product_ingredients.get(pid)]
        n = len(pids_with_data)
        if n == 0:
            continue
        freq: dict[str, int] = {}
        for pid in pids_with_data:
            for name in set(product_ingredients[pid]):
                freq[name] = freq.get(name, 0) + 1
        threshold = max(n - 1, 1)
        for name, count in freq.items():
            is_common[(category, name)] = count >= threshold
    return is_common


def main():
    OUT_DIR.mkdir(exist_ok=True)

    global STANDARD_NAME_MAP
    STANDARD_NAME_MAP = load_standard_name_map()
    print(f"standard name map: {len(STANDARD_NAME_MAP)} entries")

    products_df, product_ingredients = build_products_dataset()
    effect_map = load_effect_mapping()
    common_flags = compute_common_flags(products_df, product_ingredients)

    all_names = sorted({name for names in product_ingredients.values() for name in names})
    ingredients_rows = []
    for name in all_names:
        meta = effect_map.loc[name] if name in effect_map.index else None
        tags = []
        if meta is not None and isinstance(meta["ingredient_tag"], str) and meta["ingredient_tag"].strip():
            tags = meta["ingredient_tag"].split("/")
        ingredients_rows.append({
            "name": name,
            "ingredient_type": meta["성분_유형"] if meta is not None else None,
            "effect_tags": "|".join(tags),
            "label_confidence": meta["label_confidence"] if meta is not None else None,
            "needs_review": bool(meta["검수필요"] == "Y") if meta is not None and pd.notna(meta["검수필요"]) else False,
            "source_frequency": int(meta["빈도(상품수)"]) if meta is not None and pd.notna(meta["빈도(상품수)"]) else None,
        })
    ingredients_df = pd.DataFrame(ingredients_rows)

    pi_rows = []
    cat_by_pid = products_df.set_index("product_id")["category"]
    for pid, names in product_ingredients.items():
        category = cat_by_pid.get(pid)
        seen = set()
        for rank, name in enumerate(names, start=1):
            if name in seen:
                continue  # 같은 상품 안에서 정규화 후 중복되는 성분명 (PK: product_id+ingredient_id)
            seen.add(name)
            pi_rows.append({
                "product_id": pid,
                "ingredient_name": name,
                "rank": rank,
                "is_common_in_category": common_flags.get((category, name), False),
            })
    product_ingredients_df = pd.DataFrame(pi_rows)

    products_df.to_csv(OUT_DIR / "products.csv", index=False)
    ingredients_df.to_csv(OUT_DIR / "ingredients.csv", index=False)
    product_ingredients_df.to_csv(OUT_DIR / "product_ingredients.csv", index=False)

    print(f"products: {len(products_df)}")
    print(f"unique ingredients: {len(ingredients_df)}")
    print(f"product_ingredients rows: {len(product_ingredients_df)}")
    matched = ingredients_df["ingredient_type"].notna().sum()
    print(f"ingredients matched to effect mapping: {matched} / {len(ingredients_df)}")


if __name__ == "__main__":
    main()
