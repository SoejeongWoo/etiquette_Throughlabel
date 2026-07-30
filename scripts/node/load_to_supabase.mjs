// data/supabase/{products,ingredients,product_ingredients}.csv를 Supabase에 적재.
// 실행 전: scripts/python/normalize_ingredients.py 로 data/supabase/*.csv 생성, .env에 SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY 설정.
import "dotenv/config";
import { createClient } from "@supabase/supabase-js";
import { parse } from "csv-parse/sync";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const ROOT = path.dirname(path.dirname(path.dirname(fileURLToPath(import.meta.url))));
const DATA_DIR = path.join(ROOT, "data", "supabase");
const BATCH_SIZE = 500;

const url = process.env.SUPABASE_URL;
const serviceKey = process.env.SUPABASE_SERVICE_ROLE_KEY;
if (!url || !serviceKey) {
  throw new Error("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY가 .env에 설정되어야 합니다.");
}
const supabase = createClient(url, serviceKey);

function readCsv(name) {
  const text = readFileSync(path.join(DATA_DIR, name), "utf-8");
  return parse(text, { columns: true, skip_empty_lines: true });
}

function toNumber(v) {
  if (v === undefined || v === null || v === "") return null;
  const n = Number(v);
  return Number.isNaN(n) ? null : n;
}

function toBool(v) {
  return v === "True" || v === "true" || v === "1";
}

async function upsertInBatches(table, rows, onConflict) {
  for (let i = 0; i < rows.length; i += BATCH_SIZE) {
    const batch = rows.slice(i, i + BATCH_SIZE);
    const { error } = await supabase.from(table).upsert(batch, { onConflict });
    if (error) throw new Error(`${table} upsert 실패 (rows ${i}-${i + batch.length}): ${error.message}`);
    console.log(`${table}: ${Math.min(i + BATCH_SIZE, rows.length)} / ${rows.length}`);
  }
}

async function main() {
  const productsRaw = readCsv("products.csv");
  const ingredientsRaw = readCsv("ingredients.csv");
  const productIngredientsRaw = readCsv("product_ingredients.csv");

  const products = productsRaw.map((r) => ({
    product_id: r.product_id,
    category: r.category,
    product_name: r.product_name,
    brand_name: r.brand_name || null,
    manufacturer: r.manufacturer || null,
    brand: r.brand || null,
    manufacturer_confidence: r.manufacturer_confidence || null,
    goods_no: r.goods_no || null,
    data_source: r.data_source,
    ml_display: toNumber(r.ml_display),
    ml_estimated_total: toNumber(r.ml_estimated_total),
    volume_unit: r.volume_unit || null,
    price_regular: toNumber(r.price_regular),
    price_sale: toNumber(r.price_sale),
    price_per_10ml: toNumber(r.price_per_10ml),
    raw_ingredient_text: r.raw_ingredient_text || null,
  }));

  const ingredients = ingredientsRaw.map((r) => ({
    name: r.name,
    ingredient_type: r.ingredient_type || null,
    effect_tags: r.effect_tags ? r.effect_tags.split("|") : [],
    label_confidence: r.label_confidence || null,
    needs_review: toBool(r.needs_review),
    source_frequency: toNumber(r.source_frequency),
  }));

  // data/supabase/*.csv가 정본(source of truth)이라 재실행할 때마다 전체를 다시 동기화한다.
  // (정규화 규칙이 바뀌면 성분명이 바뀌어서, 지우지 않고 upsert만 하면 예전 이름의
  // 행이 고아로 남아 중복이 생긴다.) FK 때문에 자식 테이블부터 지운다.
  async function clearTable(table, pkColumn) {
    const { error } = await supabase.from(table).delete().not(pkColumn, "is", null);
    if (error) throw new Error(`${table} 초기화 실패: ${error.message}`);
  }
  await clearTable("product_ingredients", "product_id");
  await clearTable("ingredients", "ingredient_id");
  await clearTable("products", "product_id");

  await upsertInBatches("products", products, "product_id");
  await upsertInBatches("ingredients", ingredients, "name");

  const idByName = new Map();
  for (let from = 0; ; from += BATCH_SIZE) {
    const { data, error } = await supabase
      .from("ingredients")
      .select("ingredient_id, name")
      .range(from, from + BATCH_SIZE - 1);
    if (error) throw new Error(`ingredients 조회 실패: ${error.message}`);
    for (const r of data) idByName.set(r.name, r.ingredient_id);
    if (data.length < BATCH_SIZE) break;
  }

  const productIngredients = [];
  const unmatchedNames = new Set();
  for (const r of productIngredientsRaw) {
    const ingredient_id = idByName.get(r.ingredient_name);
    if (ingredient_id === undefined) {
      unmatchedNames.add(r.ingredient_name);
      continue;
    }
    productIngredients.push({
      product_id: r.product_id,
      ingredient_id,
      rank: toNumber(r.rank),
      is_common_in_category: toBool(r.is_common_in_category),
    });
  }
  if (unmatchedNames.size > 0) {
    console.warn(`ingredient_id 매칭 실패로 건너뜀: ${unmatchedNames.size}개`, [...unmatchedNames].slice(0, 10));
  }

  await upsertInBatches("product_ingredients", productIngredients, "product_id,ingredient_id");

  console.log("적재 완료:", {
    products: products.length,
    ingredients: ingredients.length,
    product_ingredients: productIngredients.length,
  });
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
