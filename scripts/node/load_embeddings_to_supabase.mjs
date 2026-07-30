// data/supabase/product_embeddings.csv (scripts/python/build_ingredient_embeddings.py 출력)를 products.embedding 컬럼에 적재.
// 실행 전: supabase/migrations/20260730150000_ingredient_embeddings.sql 적용 필요.
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";
import { parse } from "csv-parse/sync";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const DATA_DIR = path.join(ROOT, "data", "supabase");
const CONCURRENCY = 20;

const url = process.env.SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !serviceKey) {
  throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, serviceKey);

// products 행은 이미 존재하므로 upsert가 아니라 update를 쓴다.
// (upsert/ON CONFLICT DO UPDATE는 충돌 여부와 무관하게 INSERT 후보 행을 먼저 구성해
// NOT NULL을 검사하기 때문에, embedding만 보내면 category 등에서 위반이 난다.)
async function updateOne(record) {
  const { error } = await supabase
    .from("products")
    .update({ embedding: record.embedding })
    .eq("product_id", record.product_id);
  if (error) throw new Error(`${record.product_id} 업데이트 실패: ${error.message}`);
}

async function main() {
  const text = readFileSync(path.join(DATA_DIR, "product_embeddings.csv"), "utf-8");
  const rows = parse(text, { columns: true, skip_empty_lines: true });

  const records = rows.map((r) => ({
    product_id: r.product_id,
    embedding: JSON.parse(r.embedding),
  }));

  let done = 0;
  for (let i = 0; i < records.length; i += CONCURRENCY) {
    const batch = records.slice(i, i + CONCURRENCY);
    await Promise.all(batch.map(updateOne));
    done += batch.length;
    console.log(`embedding: ${done} / ${records.length}`);
  }

  console.log("임베딩 적재 완료:", records.length);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
