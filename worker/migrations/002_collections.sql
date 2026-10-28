-- A collection is one independent index. The same document can be stored in several
-- collections, each built with a different indexing strategy, so they can be compared.
-- Existing rows are placed in the 'baseline' collection, so nothing needs re-embedding.

ALTER TABLE documents ADD COLUMN IF NOT EXISTS collection TEXT NOT NULL DEFAULT 'baseline';

-- Uniqueness moves from "one row per file" to "one row per file per collection".
ALTER TABLE documents DROP CONSTRAINT IF EXISTS documents_file_hash_key;
CREATE UNIQUE INDEX IF NOT EXISTS documents_collection_hash_idx ON documents (collection, file_hash);
CREATE INDEX IF NOT EXISTS documents_source_idx ON documents (source);
