import type { Db } from "../db.js";

export interface FolderRow {
  id: string;
  name: string;
  parent_id: string | null;
  created_at: string;
}

/** Every query below filters by owner_id, so a folder id that belongs to someone else behaves as if it does not exist. */

export async function getFolder(db: Db, ownerId: string, id: string): Promise<FolderRow | null> {
  const result = await db.query<FolderRow>(
    "SELECT id, name, parent_id, created_at FROM folders WHERE id = $1 AND owner_id = $2",
    [id, ownerId],
  );
  return result.rows[0] ?? null;
}

/** The folders directly inside `parentId` (or at the top level when it is null), A to Z. */
export async function listChildren(db: Db, ownerId: string, parentId: string | null): Promise<FolderRow[]> {
  const result = await db.query<FolderRow>(
    `SELECT id, name, parent_id, created_at FROM folders
     WHERE owner_id = $1 AND parent_id IS NOT DISTINCT FROM $2::uuid
     ORDER BY lower(name)`,
    [ownerId, parentId],
  );
  return result.rows;
}

/** The path from the top level down to this folder, for the breadcrumb bar. */
export async function breadcrumbs(db: Db, ownerId: string, id: string): Promise<{ id: string; name: string }[]> {
  const result = await db.query<{ id: string; name: string }>(
    `WITH RECURSIVE up AS (
       SELECT id, name, parent_id, 0 AS depth FROM folders WHERE id = $1 AND owner_id = $2
       UNION ALL
       SELECT f.id, f.name, f.parent_id, up.depth + 1 FROM folders f JOIN up ON f.id = up.parent_id WHERE f.owner_id = $2
     )
     SELECT id, name FROM up ORDER BY depth DESC`,
    [id, ownerId],
  );
  return result.rows;
}

/** Throws a unique violation if a folder with this name (any capitalisation) already exists there. */
export async function createFolder(db: Db, ownerId: string, parentId: string | null, name: string): Promise<FolderRow> {
  const result = await db.query<FolderRow>(
    "INSERT INTO folders (owner_id, parent_id, name) VALUES ($1, $2, $3) RETURNING id, name, parent_id, created_at",
    [ownerId, parentId, name],
  );
  return result.rows[0]!;
}

/**
 * Deletes the folder, everything inside it, and those files' chunks (the database cascades).
 * Returns the stored file paths so the caller can delete them from disk, or null if there was no such folder.
 */
export async function deleteFolder(db: Db, ownerId: string, id: string): Promise<string[] | null> {
  const result = await db.query<{ deleted: string; paths: string[] }>(
    `WITH tree AS (SELECT folder_subtree($1, $2) AS id),
          paths AS (SELECT storage_path FROM documents WHERE owner_id = $2 AND storage_path IS NOT NULL
                    AND folder_id IN (SELECT id FROM tree)),
          gone AS (DELETE FROM folders WHERE id = $1 AND owner_id = $2 RETURNING id)
     SELECT (SELECT count(*) FROM gone) AS deleted,
            COALESCE((SELECT json_agg(storage_path) FROM paths), '[]'::json) AS paths`,
    [id, ownerId],
  );
  const row = result.rows[0]!;
  return Number(row.deleted) === 0 ? null : row.paths;
}
