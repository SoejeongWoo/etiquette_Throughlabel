// 기준 제품(product_id)과 성분/효과가 비슷한 제품을 코사인 유사도 + 필터로 검색.
// 사용법: node scripts/search_similar_products.mjs <product_id> [category] [minPrice] [maxPrice] [limit]
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";

const url = process.env.SUPABASE_URL;
const key = process.env.SUPABASE_SERVICE_ROLE_KEY || process.env.SUPABASE_ANON_KEY;
if (!url || !key) {
  throw new Error("SUPABASE_URL / SUPABASE_(SERVICE_ROLE|ANON)_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, key);

const [, , anchorId, categoryFilter, minPrice, maxPrice, limit] = process.argv;
if (!anchorId) {
  console.error("사용법: node scripts/search_similar_products.mjs <product_id> [category] [minPrice] [maxPrice] [limit]");
  process.exit(1);
}

function parseEmbedding(value) {
  return typeof value === "string" ? JSON.parse(value) : value;
}

async function main() {
  const { data: anchor, error: anchorError } = await supabase
    .from("products")
    .select("product_id, product_name, category, embedding")
    .eq("product_id", anchorId)
    .single();
  if (anchorError) throw new Error(anchorError.message);
  if (!anchor.embedding) throw new Error("이 제품은 아직 임베딩이 없습니다 (load_embeddings_to_supabase.mjs 먼저 실행).");

  const { data, error } = await supabase.rpc("match_products", {
    query_embedding: parseEmbedding(anchor.embedding),
    match_category: categoryFilter || null,
    min_price: minPrice ? Number(minPrice) : null,
    max_price: maxPrice ? Number(maxPrice) : null,
    match_count: limit ? Number(limit) : 10,
    exclude_product_id: anchorId,
  });
  if (error) throw new Error(error.message);

  console.log(`기준 제품: ${anchor.product_name} (${anchor.category})`);
  console.table(data.map((d) => ({ ...d, similarity: Number(d.similarity).toFixed(4) })));
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
