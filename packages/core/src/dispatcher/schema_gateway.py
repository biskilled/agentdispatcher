"""Separate gateway credentials and private LiteLLM schema, migration 5."""

SQL_GATEWAY = """
ALTER TABLE mng_sdk_keys ADD COLUMN IF NOT EXISTS purpose text NOT NULL DEFAULT 'ingest';
ALTER TABLE mng_sdk_keys ADD COLUMN IF NOT EXISTS allowed_models text[] NOT NULL DEFAULT '{}';
DO $$ BEGIN
 IF NOT EXISTS(SELECT FROM pg_roles WHERE rolname='dispatcher_gateway') THEN
   CREATE ROLE dispatcher_gateway NOLOGIN NOSUPERUSER NOBYPASSRLS;
 END IF;
END $$;
CREATE SCHEMA IF NOT EXISTS litellm AUTHORIZATION dispatcher_gateway;
"""
