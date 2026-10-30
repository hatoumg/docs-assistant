import type { Db } from "../db.js";

export type FileStatus = "processing" | "ready" | "failed";

export interface FileRow {
  id: number;
  name: string;
  folder_id: string;
  status: FileStatus;
  error: string | null;
  size_bytes: string | null;
  created_at: string;
  storage_path: string | null;
}

const COLUMNS = "id, name, folder_id, status, error, size_bytes, created_at, storage_path";

export async function listFiles(db: Db, ownerId: string, folderId: string): Promise<FileRow[]> {
  const result = await db.query<FileRow>(
    `SELECT ${COLUMNS} FROM documents WHERE owner_id = $1 AND folder_id = $2 ORDER BY lower(name)`,
    [ownerId, folderId],
  );
  return result.rows;
}

export async function getFile(db: Db, ownerId: string, id: number): Promise<FileRow | null> {
  const result = await db.query<FileRow>(`SELECT ${COLUMNS} FROM documents WHERE id = $1 AND owner_id = $2`, [id, ownerId]);
  return result.rows[0] ?? null;
}

export async function countFiles(db: Db, ownerId: string): Promise<number> {
  const result = await db.query<{ n: string }>("SELECT count(*) AS n FROM documents WHERE owner_id = $1", [ownerId]);
  return Number(result.rows[0]!.n);
}

/** Starts as 'processing'. Throws a unique violation if the folder already has a file with this name. */
export async function insertFile(
  db: Db,
  file: { ownerId: string; folderId: string; name: string; hash: string; sizeBytes: number; storagePath: string },
): Promise<FileRow> {
  const result = await db.query<FileRow>(
    `INSERT INTO documents (owner_id, folder_id, name, source, file_hash, size_bytes, storage_path, status)
     VALUES ($1, $2, $3, 'uploads', $4, $5, $6, 'processing') RETURNING ${COLUMNS}`,
    [file.ownerId, file.folderId, file.name, file.hash, file.sizeBytes, file.storagePath],
  );
  return result.rows[0]!;
}

export async function markFailed(db: Db, id: number, message: string): Promise<void> {
  await db.query("UPDATE documents SET status = 'failed', error = $2 WHERE id = $1", [id, message.slice(0, 300)]);
}

/** Deletes the file and its chunks. Returns the stored path, or undefined if there was no such file. */
export async function deleteFile(db: Db, ownerId: string, id: number): Promise<{ storagePath: string | null } | undefined> {
  const result = await db.query<{ storage_path: string | null }>(
    "DELETE FROM documents WHERE id = $1 AND owner_id = $2 RETURNING storage_path",
    [id, ownerId],
  );
  const row = result.rows[0];
  return row ? { storagePath: row.storage_path } : undefined;
}

/**
 * The files a question may read: everything of this user's in the folder and all folders below it
 * (or everything they own when folderId is null). Only 'ready' files can be searched.
 */
export async function searchableScope(db: Db, ownerId: string, folderId: string | null): Promise<{ ready: number[]; pending: number; failed: number }> {
  const result = await db.query<{ id: number; status: FileStatus }>(
    `SELECT id, status FROM documents
     WHERE owner_id = $1 AND ($2::uuid IS NULL OR folder_id IN (SELECT folder_subtree($2::uuid, $1)))`,
    [ownerId, folderId],
  );
  return {
    ready: result.rows.filter((r) => r.status === "ready").map((r) => r.id),
    pending: result.rows.filter((r) => r.status === "processing").length,
    failed: result.rows.filter((r) => r.status === "failed").length,
  };
}

/** For citations: which folder holds each of these files (only the owner's). */
export async function foldersOf(db: Db, ownerId: string, ids: number[]): Promise<Map<number, string>> {
  if (ids.length === 0) return new Map();
  const result = await db.query<{ id: number; folder_id: string }>(
    "SELECT id, folder_id FROM documents WHERE owner_id = $1 AND id = ANY($2::int[])",
    [ownerId, ids],
  );
  return new Map(result.rows.map((r) => [r.id, r.folder_id]));
}

/** Files stuck in 'processing' (the indexing service stopped, say) are marked failed so the user can retry. */
export async function failStuckFiles(db: Db, olderThanMinutes = 15): Promise<number> {
  const result = await db.query(
    `UPDATE documents SET status = 'failed', error = 'Indexing was interrupted. Delete this file and upload it again.'
     WHERE owner_id IS NOT NULL AND status = 'processing' AND created_at < now() - ($1::int * interval '1 minute')`,
    [olderThanMinutes],
  );
  return result.rowCount;
}
