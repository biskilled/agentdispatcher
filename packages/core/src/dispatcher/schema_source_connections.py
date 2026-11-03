"""Classify reporting credentials for source-specific management, migration 17."""

SQL_SOURCE_CONNECTIONS = """
ALTER TABLE mng_sdk_keys ADD COLUMN IF NOT EXISTS source_type text NOT NULL DEFAULT 'sdk'
CHECK (source_type IN ('sdk','codex','claude','mcp'));
"""
