-- 누군가 대시보드에서 products/ingredients/product_ingredients에 RLS를 켰는데
-- 정책이 하나도 없어서 anon/authenticated가 조회 시 항상 빈 결과를 받고 있었다.
-- (GRANT만으로는 RLS를 못 뚫는다 — RLS enabled + 정책 없음 = 기본적으로 전부 차단)
-- 쓰기는 여전히 정책이 없으므로 service_role만 가능(RLS 우회).

create policy "public read access" on products
  for select to anon, authenticated using (true);

create policy "public read access" on ingredients
  for select to anon, authenticated using (true);

create policy "public read access" on product_ingredients
  for select to anon, authenticated using (true);
