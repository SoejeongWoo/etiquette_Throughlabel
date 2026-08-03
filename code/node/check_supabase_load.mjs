// products/ingredients/product_ingredients 적재 상태 점검: 행 수 + 빠른 이상 데이터 체크.
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";

const url = process.env.SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !serviceKey) {
  throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, serviceKey);

async function count(table, filterFn) {
  let q = supabase.from(table).select("*", { count: "exact", head: true });
  if (filterFn) q = filterFn(q);
  const { count: n, error } = await q;
  if (error) throw new Error(`${table} count 실패: ${error.message}`);
  return n;
}

async function main() {
  console.log("=== 행 수 ===");
  const productsCount = await count("products");
  const ingredientsCount = await count("ingredients");
  const productIngredientsCount = await count("product_ingredients");
  console.log({ products: productsCount, ingredients: ingredientsCount, product_ingredients: productIngredientsCount });

  console.log("\n=== 이상 데이터 점검 ===");
  const nullProductName = await count("products", (q) => q.is("product_name", null));
  const nullCategory = await count("products", (q) => q.is("category", null));
  const nullPricePer10ml = await count("products", (q) => q.is("price_per_10ml", null));
  const negativePricePer10ml = await count("products", (q) => q.lt("price_per_10ml", 0));
  const nullIngredientName = await count("ingredients", (q) => q.is("name", null));
  const nullIngredientId = await count("product_ingredients", (q) => q.is("ingredient_id", null));

  console.log({
    "products.product_name IS NULL": nullProductName,
    "products.category IS NULL": nullCategory,
    "products.price_per_10ml IS NULL": nullPricePer10ml,
    "products.price_per_10ml < 0": negativePricePer10ml,
    "ingredients.name IS NULL": nullIngredientName,
    "product_ingredients.ingredient_id IS NULL": nullIngredientId,
  });

  console.log("\n=== 샘플 3건 (products) ===");
  const { data: sample, error: sampleErr } = await supabase
    .from("products")
    .select("product_id, product_name, category, price_per_10ml, raw_ingredient_text")
    .limit(3);
  if (sampleErr) throw new Error(`샘플 조회 실패: ${sampleErr.message}`);
  console.log(sample);
}

main().catch((err) => {
  console.error("체크 실패:", err);
  process.exit(1);
});
