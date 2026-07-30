# BARE fit — 라벨 스캔 기반 스킨케어 어시스턴트

## 개요
ODM 중심 K-뷰티 생산 구조상, 동일 공장에서 생산된 제품이 브랜드에 따라 최대 5배까지 가격 차이가 발생한다(예: 동일 제조사 추정 선크림 1.8만~10만 원대). 라벨 뒷면에는 전성분·제조사 정보가 이미 기재되어 있지만 소비자는 브랜드·광고 이미지에만 의존해 구매를 결정한다. BARE fit은 이 정보 비대칭을 해소하여 소비자가 이미 가진 제품을 기준으로 합리적인 대안과 활용법을 찾도록 돕는다.

## 핵심 가치
1. 스캔 1장으로 제품 등록
2. 같은 공장 대안 제품 탐색 및 절약 가능 금액 계산
3. 날씨 기반 오늘의 루틴 추천
4. 구매 전이 아닌 "이미 가진 제품"에서 출발

## 파이프라인 (STEP)
| STEP | 내용 | 산출물 |
|---|---|---|
| 1. 패키지 스캔 | 라벨 OCR로 전성분·제조판매업자·유통업체 추출, 국내 라벨 규격 패턴 매칭으로 정확도 보완 | `ocr_result` |
| 2. 제조사 DB | 제조사 정보 기반 '같은 공장' 브랜드 자동 매핑, 브랜드-OEM/ODM 연결망 구조화 | `manufacturer_map` |
| 3. 성분 태깅 | LLM으로 보습·자외선 차단·저자극 등 기능 태그 부여 | `ingredient_tag` |
| 4. 날씨+추천 | OpenWeather API(온도·자외선지수·습도·미세먼지) 기반 보유 제품 적합도 산출 및 오늘의 조합 추천 | `weather_data`, `fit_score`, `daily_recommendation` |

## 핵심 화면
- **FEATURE 01 날씨 기반 추천**: 오늘 날씨 4종 지표 + 보유 제품 적합도(`fit_score`) + 추천 사유 1줄
- **FEATURE 02 같은 제조사 탐색**: 스캔 제품 → 제조사 확인 → 같은 공장 브랜드 목록 + 가격 + `saving_amount`

## 도메인 규칙
- OEM(브랜드 주도 처방/디자인)과 ODM(제조사 주도 R&D~디자인)을 구분한다.
- "화장품제조업자"(공장)와 "화장품책임판매업자"(브랜드)를 구분한다.
- 성분 비교는 전성분(INCI) 기준이며, 성분 순서는 함량 순서(1% 이하 제외)를 전제로 한다.
- 같은 제조사·유사 전성분이어도 "동일 제품"으로 단정하지 않고 "같은 공장에서 생산된 대안 제품" 수준으로만 표현한다(법적 리스크 관리).
- 브랜드-제조사 매핑은 라벨·공개 정보로 검증된 것만 사실로 취급하며, 미검증 시 "확인 필요"로 표기한다.
- 의학적 효능 단정, 특정 브랜드 비방·가격 후려치기 뉘앙스를 금지한다. 톤은 "합리적 선택 지원"을 유지한다.
- OCR·LLM 태깅·적합도 점수는 오류 가능성이 있으므로 confidence 값과 검수 플로우를 항상 포함한다.
- `fit_score`·`saving_amount`는 산출 근거(날씨 지표, 가격 출처)를 함께 제시할 수 있는 구조로 설계한다.

## 데이터 스키마 용어
- `manufacturer`: 실제 생산 공장 / `brand`: 책임판매업자
- `ocr_result`, `ingredient_tag`, `manufacturer_map`, `weather_data`, `fit_score`, `saving_amount`, `daily_recommendation`

## 이 저장소(olive_crwl)의 역할
STEP1(스캔)~STEP2(제조사 DB)를 위한 원천 데이터를 실제 카메라 OCR 대신 올리브영 웹 크롤링으로
선행 확보한다. 상품 상세페이지의 "상품정보 제공고시"에서 전성분과 제조사/책임판매업자 원문을
가져와 파싱하며, 라벨 이미지가 아닌 웹 텍스트가 출처이므로 각 상품 레코드에 `data_source`를
명시해 실제 OCR 결과(`ocr_result`)와 혼동되지 않도록 한다.

### 산출물
- `products.csv` / `products.xlsx` — 상품 1건당 1행: `product_id`, `category`, `product_name`, `brand_name`, `manufacturer`, `brand`, `manufacturer_confidence`, `ingredient`, `data_source`
- `reviews.csv` / `reviews.xlsx` — 리뷰 1건당 1행, `product_id`로 products와 연결
- `manufacturer_map.json` — STEP2 산출물. `manufacturer_confidence=high`인 상품만으로 제조사 기준 브랜드 그룹화, `has_alternative`(같은 공장을 공유하는 서로 다른 브랜드 2개 이상 여부) 포함

### 실행
`olive_crwl_clean.ipynb`의 셀을 순서대로 실행하면 `CATEGORY_IDS`에 등록된 카테고리를 크롤링하여 위 세 산출물을 생성한다. 규모 조절(`max_products`, `max_reviews_per_product`)과 카테고리 추가 방법은 노트북 하단 안내 셀을 참고한다.
