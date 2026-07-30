-- BARE fit product DB schema
-- Sources: products.csv (olive_crwl 전성분 크롤링) + 8개 카테고리 price_ingredient 테이블
-- 성분명은 scripts/normalize_ingredients.py 로 정규화된 값을 적재한다.

create extension if not exists pgcrypto;

-- 성분 사전: 정규화된 성분명 1개 = 1행. 승민 작업물(ingredient_effect_mapping)의 효과 태그를 함께 보관.
create table ingredients (
  ingredient_id bigint generated always as identity primary key,
  name text not null unique,
  ingredient_type text,              -- 액티브 / UV필터 / 기제 / 향료 / 착색제
  effect_tags text[] not null default '{}',   -- 보습/진정 등 ingredient_tag를 '/' 기준으로 분리
  label_confidence text,             -- high / low (ingredient_effect_mapping 출처)
  needs_review boolean not null default false,
  source_frequency integer,          -- ingredient_effect_mapping 상 등장 상품 수 (참고용)
  created_at timestamptz not null default now()
);

-- 제품: products.csv + 8개 카테고리 price_ingredient 테이블을 하나의 스키마로 통합.
-- 두 원본은 스키마가 달라 goods_no로만 부분적으로 조인 가능하다는 점에 유의 (README 참고).
create table products (
  product_id text primary key,
  category text not null,
  product_name text not null,
  brand_name text,
  manufacturer text,                 -- 화장품제조업자 (공장)
  brand text,                        -- 화장품책임판매업자
  manufacturer_confidence text,      -- high / medium / low
  goods_no text,
  data_source text not null,         -- 'olive_crwl_products' | 'olive_crwl_price_ingredient'
  ml_display numeric,                -- ml_표시용량
  ml_estimated_total numeric,        -- ml_추정총용량
  volume_unit text,
  price_regular numeric,
  price_sale numeric,
  price_per_10ml numeric,
  raw_ingredient_text text,          -- 원본 스크래핑 텍스트 (감사/재파싱용)
  created_at timestamptz not null default now()
);
create index products_category_idx on products (category);
create index products_goods_no_idx on products (goods_no);

-- 제품-성분 조합 (정규화 파이프라인 산출물)
create table product_ingredients (
  product_id text not null references products (product_id) on delete cascade,
  ingredient_id bigint not null references ingredients (ingredient_id) on delete cascade,
  rank integer,                      -- 해당 제품 전성분표 내 순번 (1-based, 함량 순서 근사치)
  is_common_in_category boolean not null default false,  -- 같은 category 내 상품의 대부분(n-1 이상)에 존재하는 성분인지
  primary key (product_id, ingredient_id)
);
create index product_ingredients_ingredient_idx on product_ingredients (ingredient_id);

comment on table ingredients is '정규화된 INCI 성분 사전. name은 scripts/normalize_ingredients.py의 clean_token() 규칙으로 정규화된 값.';
comment on table products is 'products.csv + 8개 카테고리 price_ingredient 테이블 통합. data_source로 원본 구분.';
comment on column product_ingredients.is_common_in_category is '원본 CSV의 공통_ingredient/차별화_ingredient 컬럼은 상품별로 값이 들쭉날쭉한 버그가 있어(README 참고) 재계산한 값을 사용한다.';
