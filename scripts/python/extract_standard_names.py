"""식약처 성분사전 '표준화명칭목록' PDF(별첨1)를 표 구조 그대로 추출해서
data/supabase/standard_ingredient_names.csv 로 저장한다. (성분코드, 표준성분명, 표준영문명, 구명칭, 구영문명)

이 CSV가 scripts/python/normalize_ingredients.py 에서 구명칭 -> 표준성분명 매핑의 기준이 된다.
"""

import sys
from pathlib import Path

import pdfplumber

PDF_PATH = Path(r"C:/Users/hayou/OneDrive/Desktop/멋사/별첨1. 표준화명칭목록_260630.pdf")
OUT_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "supabase" / "standard_ingredient_names.csv"

COLUMNS = ["ingredient_code", "standard_name_kr", "standard_name_en", "alias_kr", "alias_en"]


def clean_cell(v):
    if v is None:
        return ""
    return v.replace("\n", "").strip()


def main():
    rows = []
    with pdfplumber.open(PDF_PATH) as pdf:
        n_pages = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            for table in page.extract_tables():
                for row in table:
                    if not row or row[0] == "성분코드":
                        continue
                    cells = [clean_cell(c) for c in row]
                    while len(cells) < 5:
                        cells.append("")
                    rows.append(cells[:5])
            if (i + 1) % 100 == 0 or i + 1 == n_pages:
                print(f"{i + 1}/{n_pages} pages, {len(rows)} rows", file=sys.stderr)

    import csv
    OUT_PATH.parent.mkdir(exist_ok=True)
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(COLUMNS)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows to {OUT_PATH}")


if __name__ == "__main__":
    main()
