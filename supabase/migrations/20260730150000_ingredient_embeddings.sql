-- 성분 조합 임베딩 컬럼 + 코사인 유사도 검색 함수.
-- scripts/build_ingredient_embeddings.py 로 생성한 768차원 벡터(jhgan/ko-sroberta-multitask)를 저장한다.

create extension if not exists vector;

alter table products add column if not exists embedding vector(768);

create index if not exists products_embedding_idx
  on products using hnsw (embedding vector_cosine_ops);

-- 코사인 유사도 검색 + 카테고리/가격 필터.
-- price_sale이 없으면 price_regular로 대체해서 가격 필터를 적용한다.
create or replace function match_products(
  query_embedding vector(768),
  match_category text default null,
  min_price numeric default null,
  max_price numeric default null,
  match_count int default 10,
  exclude_product_id text default null
)
returns table (
  product_id text,
  product_name text,
  category text,
  brand_name text,
  price_sale numeric,
  price_regular numeric,
  price_per_10ml numeric,
  similarity double precision
)
language sql stable
as $$
  select
    p.product_id,
    p.product_name,
    p.category,
    p.brand_name,
    p.price_sale,
    p.price_regular,
    p.price_per_10ml,
    1 - (p.embedding <=> query_embedding) as similarity
  from products p
  where p.embedding is not null
    and (match_category is null or p.category = match_category)
    and (min_price is null or coalesce(p.price_sale, p.price_regular) >= min_price)
    and (max_price is null or coalesce(p.price_sale, p.price_regular) <= max_price)
    and (exclude_product_id is null or p.product_id <> exclude_product_id)
  order by p.embedding <=> query_embedding
  limit match_count;
$$;

grant execute on function match_products to anon, authenticated, service_role;
