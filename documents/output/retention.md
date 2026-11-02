# Retention and workspace deletion

Automatic attribution expiry is disabled by default. A tenant owner/admin can set
an explicit horizon in **Access → Attribution retention**. The worker processes
bounded batches (`DISPATCHER_RETENTION_BATCH_ROWS`, default 1,000 per table/tick),
with row locks and tenant RLS. Policy changes and applied batches are audited.

Expired usage and overlapping observations lose end-user, verified-user, session,
trace, job, project, work-item, pipeline-role and configuration attribution. Financial
measurements, costs/currencies, provider/model/app/environment, pricing evidence and
idempotency hashes remain. Dashboard/export rows identify expired attribution.
This preserves accounting and prevents old event replays from recreating a charge.
It deliberately does not erase every workspace record: policies, audit, configuration,
scheduler definitions, identities and financial evidence have separate lifecycles.

Choose a horizon that covers required historical attribution reports. Disabling or
extending a policy cannot reconstruct expired attribution. A backup can restore an
earlier state; it must remain subject to the operator's deletion/retention process.

## Complete workspace deletion

Use the offline operator tool with the same private operator environment as recovery:

```sh
python -m dispatcher.tenant_admin --tenant TENANT_UUID --confirm-tenant TENANT_UUID
```

For the optional recovery image, override its entrypoint to `python`, then pass
`-m dispatcher.tenant_admin` and the same arguments. The tool requires
`DISPATCHER_RECOVERY_DATABASE_URL` and operator privileges. It is not exposed through
SDK keys or a public HTTP endpoint. A different or missing confirmation UUID fails
before deletion.

The command locks the tenant and deletes tenant-owned management/memory records in
foreign-key order inside one transaction. Unsupported dependency cycles or database
errors roll back the operation. It never drops a database or truncates shared tables.
Other tenants and shared user identities remain; a user may belong to other
workspaces. Analytics bindings, service credentials, memberships and tenant tool
grants are removed with the tenant, so prior credentials cannot recover access.

Keep the returned deletion receipt in the operator's audit process. Existing backups,
upstream provider records and application-owned YAML repositories are not rewritten.
Apply approved deletions again before exposing a restoration from an older backup.
Erase backups through their encrypted storage retention policy. This is workspace
deletion, not deletion of a shared login identity across all workspaces.

Two-tenant PostgreSQL tests verify expiry concurrency, unchanged charges, replay
protection, authorization, explicit deletion confirmation and unaffected surviving
tenant access. No real workspace is deleted by these tests.
