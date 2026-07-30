-- Supabase 최신 기본값은 public 스키마의 새 테이블을 anon/authenticated/service_role에
-- 자동으로 노출하지 않는다. 적재 스크립트(service_role)와 추후 조회(anon/authenticated)를
-- 위해 명시적으로 권한을 부여한다.

grant usage on schema public to anon, authenticated, service_role;

grant select on products, ingredients, product_ingredients to anon, authenticated;
grant all on products, ingredients, product_ingredients to service_role;

grant all on all sequences in schema public to service_role;

alter default privileges in schema public grant select on tables to anon, authenticated;
alter default privileges in schema public grant all on tables to service_role;
alter default privileges in schema public grant all on sequences to service_role;
