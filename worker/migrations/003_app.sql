-- Accounts, folders and per-user documents for the web app.
--
-- migrate.py runs every file in this folder each time, so everything here is safe to run again.
--
-- The rules the database itself enforces (so a bug in the API cannot break them):
--   * a folder's parent must belong to the same user
--   * a document's folder must belong to the same user
--   * deleting a user deletes their folders, and deleting a folder deletes its subfolders and files (and chunks)
--   * a document is either part of the evaluation data (no owner, no folder) or owned and inside a folder

CREATE TABLE IF NOT EXISTS users (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    email text NOT NULL,
    name text NOT NULL DEFAULT '',
    provider text NOT NULL DEFAULT 'password',
    provider_account_id text,
    password_hash text,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT users_provider_check CHECK (provider IN ('password', 'google')),
    CONSTRAINT users_credentials_check CHECK (
        (provider = 'password' AND password_hash IS NOT NULL AND provider_account_id IS NULL)
        OR (provider <> 'password' AND password_hash IS NULL AND provider_account_id IS NOT NULL)
    )
);
CREATE UNIQUE INDEX IF NOT EXISTS users_email_idx ON users (lower(email));
CREATE UNIQUE INDEX IF NOT EXISTS users_provider_idx ON users (provider, provider_account_id) WHERE provider_account_id IS NOT NULL;

CREATE TABLE IF NOT EXISTS folders (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    owner_id uuid NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    parent_id uuid,
    name text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now(),
    CONSTRAINT folders_name_check CHECK (length(btrim(name)) BETWEEN 1 AND 120),
    CONSTRAINT folders_id_owner_key UNIQUE (id, owner_id),
    CONSTRAINT folders_parent_fk FOREIGN KEY (parent_id, owner_id) REFERENCES folders (id, owner_id) ON DELETE CASCADE,
    CONSTRAINT folders_not_own_parent CHECK (parent_id IS NULL OR parent_id <> id)
);
CREATE INDEX IF NOT EXISTS folders_parent_idx ON folders (parent_id);
-- No two folders with the same name side by side (the all-zero id stands in for "top level").
CREATE UNIQUE INDEX IF NOT EXISTS folders_sibling_name_idx
    ON folders (owner_id, COALESCE(parent_id, '00000000-0000-0000-0000-000000000000'::uuid), lower(btrim(name)));

-- Documents: the evaluation data keeps working untouched (owner_id and folder_id stay empty).
ALTER TABLE documents ADD COLUMN IF NOT EXISTS owner_id uuid;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS folder_id uuid;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS status text NOT NULL DEFAULT 'ready';
ALTER TABLE documents ADD COLUMN IF NOT EXISTS error text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS storage_path text;
ALTER TABLE documents ADD COLUMN IF NOT EXISTS size_bytes bigint;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_status_check') THEN
        ALTER TABLE documents ADD CONSTRAINT documents_status_check CHECK (status IN ('processing', 'ready', 'failed'));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_scope_check') THEN
        ALTER TABLE documents ADD CONSTRAINT documents_scope_check CHECK ((owner_id IS NULL) = (folder_id IS NULL));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'documents_folder_fk') THEN
        ALTER TABLE documents ADD CONSTRAINT documents_folder_fk
            FOREIGN KEY (folder_id, owner_id) REFERENCES folders (id, owner_id) ON DELETE CASCADE;
    END IF;
END
$$;

-- The "same file only once" rule from 002 now applies to evaluation documents only.
-- Different users (or different folders) may each hold the same file.
DROP INDEX IF EXISTS documents_collection_hash_idx;
CREATE UNIQUE INDEX documents_collection_hash_idx ON documents (collection, file_hash) WHERE owner_id IS NULL;
CREATE UNIQUE INDEX IF NOT EXISTS documents_folder_name_idx ON documents (folder_id, lower(name)) WHERE folder_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS documents_owner_idx ON documents (owner_id, folder_id);

-- Every folder at or below `root` that belongs to `for_owner`, including `root` itself.
-- (UNION, not UNION ALL, so even a broken loop in the data could not run forever.)
CREATE OR REPLACE FUNCTION folder_subtree(root uuid, for_owner uuid) RETURNS SETOF uuid
LANGUAGE sql STABLE AS $$
    WITH RECURSIVE tree AS (
        SELECT id FROM folders WHERE id = root AND owner_id = for_owner
        UNION
        SELECT f.id FROM folders f JOIN tree t ON f.parent_id = t.id WHERE f.owner_id = for_owner
    )
    SELECT id FROM tree
$$;
