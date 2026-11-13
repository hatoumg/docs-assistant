-- The kind of document the user said they were uploading (general, technical, report, paper, contract, legal, policy).
-- It chooses how the file is cut into chunks (DOC_TYPES in worker/1_indexing/3_chunk.py).
-- NULL means the user let the app decide: CHUNK_METHOD in worker/common/config.py is used.
ALTER TABLE documents ADD COLUMN IF NOT EXISTS doc_type text;
