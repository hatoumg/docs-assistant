import type { Db } from "../db.js";

export interface User {
  id: string;
  email: string;
  name: string;
}

export interface Credentials extends User {
  provider: string;
  password_hash: string | null;
}

const PUBLIC = "id, email, name";

export async function createPasswordUser(db: Db, email: string, name: string, passwordHash: string): Promise<User> {
  const result = await db.query<User>(
    `INSERT INTO users (email, name, provider, password_hash) VALUES ($1, $2, 'password', $3) RETURNING ${PUBLIC}`,
    [email, name, passwordHash],
  );
  return result.rows[0]!;
}

export async function createOAuthUser(db: Db, provider: string, accountId: string, email: string, name: string): Promise<User> {
  const result = await db.query<User>(
    `INSERT INTO users (email, name, provider, provider_account_id) VALUES ($1, $2, $3, $4) RETURNING ${PUBLIC}`,
    [email, name, provider, accountId],
  );
  return result.rows[0]!;
}

export async function findByEmail(db: Db, email: string): Promise<Credentials | null> {
  const result = await db.query<Credentials>(
    `SELECT ${PUBLIC}, provider, password_hash FROM users WHERE lower(email) = lower($1)`,
    [email],
  );
  return result.rows[0] ?? null;
}

export async function findByProvider(db: Db, provider: string, accountId: string): Promise<User | null> {
  const result = await db.query<User>(
    `SELECT ${PUBLIC} FROM users WHERE provider = $1 AND provider_account_id = $2`,
    [provider, accountId],
  );
  return result.rows[0] ?? null;
}

export async function getUser(db: Db, id: string): Promise<User | null> {
  const result = await db.query<User>(`SELECT ${PUBLIC} FROM users WHERE id = $1`, [id]);
  return result.rows[0] ?? null;
}
