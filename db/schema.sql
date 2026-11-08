-- Fiber@Home Knowledge Intelligence Platform — PostgreSQL 16 schema (v1)
-- Idempotent. pgvector is optional: embeddings are enabled only if the extension exists.
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS pgcrypto;
DO $$ BEGIN
  BEGIN CREATE EXTENSION IF NOT EXISTS vector; EXCEPTION WHEN OTHERS THEN RAISE NOTICE 'pgvector not available: semantic search disabled'; END;
END $$;

DO $$ BEGIN CREATE TYPE app_role AS ENUM ('admin','editor','reviewer','viewer'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;
DO $$ BEGIN CREATE TYPE doc_status AS ENUM ('draft','review','approved','published','superseded','archived'); EXCEPTION WHEN duplicate_object THEN NULL; END $$;

CREATE TABLE IF NOT EXISTS departments(
  id text PRIMARY KEY, name text NOT NULL, poc text, created_at timestamptz NOT NULL DEFAULT now());

CREATE TABLE IF NOT EXISTS users(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  email text UNIQUE NOT NULL, display_name text NOT NULL,
  idp_subject text UNIQUE,                 -- Entra ID 'oid'/'sub' when SSO is used
  password_hash text,                      -- only for the break-glass local admin; NULL for SSO users
  is_active boolean NOT NULL DEFAULT true, failed_logins int NOT NULL DEFAULT 0, locked_until timestamptz,
  created_at timestamptz NOT NULL DEFAULT now());

-- dept_id NULL = organisation-wide role
CREATE TABLE IF NOT EXISTS user_roles(
  user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  dept_id text REFERENCES departments(id), role app_role NOT NULL,
  UNIQUE NULLS NOT DISTINCT (user_id, dept_id, role));

CREATE TABLE IF NOT EXISTS sessions(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  token_hash bytea UNIQUE NOT NULL, csrf_hash bytea NOT NULL,
  created_at timestamptz NOT NULL DEFAULT now(), last_seen timestamptz NOT NULL DEFAULT now(),
  expires_at timestamptz NOT NULL, revoked boolean NOT NULL DEFAULT false);

-- One-time sign-in codes (email OTP). Only a keyed hash of the code is stored; codes are single-use, expire and lock after repeated failures.
CREATE TABLE IF NOT EXISTS login_codes(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), user_id uuid NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  code_hash bytea NOT NULL, created_at timestamptz NOT NULL DEFAULT now(), expires_at timestamptz NOT NULL,
  attempts int NOT NULL DEFAULT 0, used boolean NOT NULL DEFAULT false);
CREATE INDEX IF NOT EXISTS login_codes_user_idx ON login_codes(user_id, created_at DESC);

-- A controlled source document (owner, source, version, status, dates)
CREATE TABLE IF NOT EXISTS documents(
  id uuid PRIMARY KEY DEFAULT gen_random_uuid(), title text NOT NULL, source text NOT NULL,
  dept_id text NOT NULL REFERENCES departments(id), owner_id uuid REFERENCES users(id),
  status doc_status NOT NULL DEFAULT 'draft', current_version int NOT NULL DEFAULT 1,
  review_due date, created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  UNIQUE (title, source));

CREATE TABLE IF NOT EXISTS document_versions(
  document_id uuid NOT NULL REFERENCES documents(id) ON DELETE CASCADE, version int NOT NULL,
  status doc_status NOT NULL DEFAULT 'draft', file_name text, mime text, sha256 text, storage_key text,
  created_by uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(),
  submitted_at timestamptz, reviewed_by uuid REFERENCES users(id), reviewed_at timestamptz,
  approved_by uuid REFERENCES users(id), approved_at timestamptz, published_at timestamptz, note text,
  PRIMARY KEY(document_id, version));

-- Atomic knowledge entry (what the assistant retrieves). Only status='published' is retrievable.
CREATE TABLE IF NOT EXISTS entries(
  id text PRIMARY KEY,                       -- legacy id S001.. preserved
  dept_id text NOT NULL REFERENCES departments(id), document_id uuid REFERENCES documents(id),
  category text NOT NULL, subcategory text, kind text NOT NULL CHECK (kind IN ('doc','qa','team')),
  title text NOT NULL, body text NOT NULL, reference text, source text NOT NULL,
  status doc_status NOT NULL DEFAULT 'published', version int NOT NULL DEFAULT 1,
  supersedes text REFERENCES entries(id), created_by uuid REFERENCES users(id),
  created_at timestamptz NOT NULL DEFAULT now(), updated_at timestamptz NOT NULL DEFAULT now(),
  tsv tsvector GENERATED ALWAYS AS (setweight(to_tsvector('english',title),'A')||setweight(to_tsvector('english',coalesce(subcategory,'')||' '||category),'B')||setweight(to_tsvector('english',body),'C')) STORED);
CREATE INDEX IF NOT EXISTS entries_tsv ON entries USING gin(tsv);
CREATE INDEX IF NOT EXISTS entries_trgm ON entries USING gin((title||' '||body) gin_trgm_ops);
CREATE INDEX IF NOT EXISTS entries_dept ON entries(dept_id,status);
DO $$ BEGIN IF EXISTS(SELECT 1 FROM pg_extension WHERE extname='vector') THEN
  EXECUTE 'ALTER TABLE entries ADD COLUMN IF NOT EXISTS embedding vector(1024)';
END IF; END $$;

CREATE TABLE IF NOT EXISTS search_events(id bigserial PRIMARY KEY, user_id uuid REFERENCES users(id), query text NOT NULL, answered boolean NOT NULL, top_entry text, n_results int NOT NULL, at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS feedback(id bigserial PRIMARY KEY, user_id uuid REFERENCES users(id), search_event bigint REFERENCES search_events(id), helpful boolean NOT NULL, comment text, at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS gaps(id bigserial PRIMARY KEY, query text NOT NULL, dept_id text REFERENCES departments(id), status text NOT NULL DEFAULT 'open' CHECK (status IN ('open','assigned','resolved')), assignee uuid REFERENCES users(id), created_at timestamptz NOT NULL DEFAULT now(), resolved_at timestamptz);

-- Append-only audit trail with a hash chain (tamper evidence)
CREATE TABLE IF NOT EXISTS audit_log(
  id bigserial PRIMARY KEY, at timestamptz NOT NULL DEFAULT now(), actor uuid, actor_email text, action text NOT NULL,
  object_type text, object_id text, detail jsonb NOT NULL DEFAULT '{}', ip inet, prev_hash text, row_hash text);
CREATE OR REPLACE FUNCTION audit_chain() RETURNS trigger AS $$
DECLARE p text;
BEGIN
  PERFORM pg_advisory_xact_lock(7001);
  SELECT row_hash INTO p FROM audit_log ORDER BY id DESC LIMIT 1;
  NEW.prev_hash := coalesce(p,'');
  NEW.row_hash := encode(digest(NEW.prev_hash||NEW.at::text||coalesce(NEW.actor_email,'')||NEW.action||coalesce(NEW.object_type,'')||coalesce(NEW.object_id,'')||NEW.detail::text,'sha256'),'hex');
  RETURN NEW; END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_chain_t ON audit_log;
CREATE TRIGGER audit_chain_t BEFORE INSERT ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_chain();
CREATE OR REPLACE FUNCTION audit_immutable() RETURNS trigger AS $$ BEGIN RAISE EXCEPTION 'audit_log is append-only'; END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS audit_no_mod ON audit_log;
CREATE TRIGGER audit_no_mod BEFORE UPDATE OR DELETE ON audit_log FOR EACH ROW EXECUTE FUNCTION audit_immutable();
