"""Permit tenant-scoped expiry of replaceable account state, migration 19."""

SQL_ACCOUNT_RETENTION = """
GRANT DELETE ON mem_account_snapshots TO dispatcher_app;
CREATE INDEX IF NOT EXISTS mem_account_snapshots_retention
 ON mem_account_snapshots(tenant_id,received_at);
"""
