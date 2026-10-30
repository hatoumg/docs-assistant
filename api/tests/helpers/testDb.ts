import { randomUUID } from "node:crypto";
import { readdir, readFile } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { createDb, type Db } from "../../src/db.js";

export interface TestDatabase {
  db: Db;
  close(): Promise<void>;
}

const MIGRATIONS = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../../../worker/migrations");

/**
 * A brand-new, empty database with every migration applied, so tests never touch your real data.
 * It is created next to the one in DATABASE_URL (the Postgres from docker compose) and deleted afterwards.
 */
export async function createTestDatabase(): Promise<TestDatabase> {
  const baseUrl = new URL(process.env.DATABASE_URL ?? "postgresql://postgres:postgres@localhost:5432/docs_assistant");
  const name = `docs_assistant_test_${randomUUID().replaceAll("-", "")}`;
  const admin = createDb(baseUrl.toString());
  await admin.query(`CREATE DATABASE ${name}`);

  const testUrl = new URL(baseUrl);
  testUrl.pathname = `/${name}`;
  const db = createDb(testUrl.toString());
  for (const file of (await readdir(MIGRATIONS)).filter((f) => f.endsWith(".sql")).sort()) {
    await db.query(await readFile(path.join(MIGRATIONS, file), "utf8"));
  }
  return {
    db,
    async close() {
      await db.end();
      await admin.query(`DROP DATABASE ${name} WITH (FORCE)`);
      await admin.end();
    },
  };
}
