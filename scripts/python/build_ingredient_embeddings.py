# data/supabase/product_ingredients.csv + ingredients.csv + products.csv 를 조합해
# 제품별 "성분 조합" 문장을 만들고, 한국어 문장임베딩 모델로 벡터화한다.
# 출력: data/supabase/product_embeddings.csv (product_id, embedding)
import csv
import json
from collections import defaultdict
from pathlib import Path

import numpy as np
from sentence_transformers import SentenceTransformer

ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = ROOT / "data" / "supabase"
MODEL_NAME = "jhgan/ko-sroberta-multitask"
TOP_N_INGREDIENTS = 20


def load_ingredient_effects():
    effects = {}
    with open(DATA_DIR / "ingredients.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            tags = [t for t in (row["effect_tags"] or "").split("|") if t]
            effects[row["name"]] = tags
    return effects


def load_categories():
    cats = {}
    with open(DATA_DIR / "products.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            cats[row["product_id"]] = row["category"]
    return cats


def load_product_ingredients():
    rows = defaultdict(list)
    with open(DATA_DIR / "product_ingredients.csv", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            try:
                rank = int(row["rank"])
            except (ValueError, KeyError):
                rank = 9999
            rows[row["product_id"]].append((rank, row["ingredient_name"]))
    for pid in rows:
        rows[pid].sort(key=lambda x: x[0])
    return rows


def build_text(category, ingredient_names, effect_map):
    top = ingredient_names[:TOP_N_INGREDIENTS]
    tags, seen = [], set()
    for name in top:
        for tag in effect_map.get(name, []):
            if tag not in seen:
                seen.add(tag)
                tags.append(tag)
    parts = [f"카테고리: {category}", f"성분: {', '.join(top)}"]
    if tags:
        parts.append(f"효과: {', '.join(tags)}")
    return " | ".join(parts)


def main():
    categories = load_categories()
    effect_map = load_ingredient_effects()
    product_ingredients = load_product_ingredients()
    product_ids = sorted(product_ingredients.keys())

    texts = [
        build_text(categories.get(pid, ""), [n for _, n in product_ingredients[pid]], effect_map)
        for pid in product_ids
    ]

    print(f"[1/3] {len(product_ids)}개 제품 텍스트 구성 완료")
    print("샘플:", texts[0][:200])

    print(f"[2/3] 모델 로딩: {MODEL_NAME}")
    model = SentenceTransformer(MODEL_NAME)

    print("[3/3] 임베딩 생성 중...")
    embeddings = model.encode(texts, batch_size=32, show_progress_bar=True, normalize_embeddings=True)

    out_path = DATA_DIR / "product_embeddings.csv"
    with open(out_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["product_id", "embedding"])
        for pid, vec in zip(product_ids, embeddings):
            writer.writerow([pid, json.dumps(vec.tolist())])

    print(f"저장 완료: {out_path} ({len(product_ids)} rows, dim={embeddings.shape[1]})")

    # --- sanity check: 같은 카테고리 쌍 vs 다른 카테고리 쌍의 유사도 비교 ---
    by_category = defaultdict(list)
    for i, pid in enumerate(product_ids):
        by_category[categories.get(pid, "")].append(i)

    same_cat_pairs, diff_cat_pairs = [], []
    cats_with_2plus = [c for c, idxs in by_category.items() if len(idxs) >= 2]
    if len(cats_with_2plus) >= 1:
        c = cats_with_2plus[0]
        i, j = by_category[c][0], by_category[c][1]
        same_cat_pairs.append((product_ids[i], product_ids[j], float(np.dot(embeddings[i], embeddings[j]))))
    if len(cats_with_2plus) >= 2:
        c1, c2 = cats_with_2plus[0], cats_with_2plus[1]
        i, j = by_category[c1][0], by_category[c2][0]
        diff_cat_pairs.append((product_ids[i], product_ids[j], float(np.dot(embeddings[i], embeddings[j]))))

    print("\n--- sanity check (코사인 유사도, normalize된 벡터라 내적=코사인) ---")
    for a, b, sim in same_cat_pairs:
        print(f"같은 카테고리 쌍  {a} vs {b}: {sim:.4f}")
    for a, b, sim in diff_cat_pairs:
        print(f"다른 카테고리 쌍  {a} vs {b}: {sim:.4f}")


if __name__ == "__main__":
    main()
