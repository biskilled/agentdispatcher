# PostgreSQL backup and recovery

The core database contains every tenant's durable product records. Backups therefore
require operator access and private storage. The runtime API/worker never receives
the owner connection. YAML repositories, deployment secrets and LiteLLM's separate
database require their own backups; this archive covers the Dispatcher database.

## Back up

With the application running and its normal `.env` configured:

```sh
docker compose --profile recovery run --build --rm recovery backup /backups/dispatcher.dump
```

`BACKUP_DIRECTORY` selects the host directory (default `./backups`, excluded from
git). Set `RECOVERY_UID`/`RECOVERY_GID` to the local operator's IDs when needed. Both
the archive and `.dump.json` manifest are created exclusively with private file
permissions. Existing files are never overwritten. Store the pair in encrypted
backup storage with your chosen retention policy. A checksum detects corruption;
it is not proof of authenticity. Restore only archives you trust.

The optional recovery image adds PostgreSQL client tools; normal app containers
remain smaller. On a host with Python/core installed and matching PostgreSQL tools,
the equivalent command is `python -m dispatcher.recovery backup <archive>`, with
`DISPATCHER_RECOVERY_DATABASE_URL` supplied through the operator's secret environment.
`DISPATCHER_PG_DUMP` and `DISPATCHER_PG_RESTORE` select client executable paths.

`pg_dump` takes a consistent data snapshot. A shared migration lock prevents schema
changes during backup. The manifest identifies the exact schema versions and checksum.
No credentials are printed or passed as command-line DSNs. A failed dump has no valid
manifest and must not be treated as a completed backup.

## Restore into a new database

Create a **new, empty, offline database** using the PostgreSQL operator account.
Use the same application release as the backup and PostgreSQL-compatible client
tools. Set `DISPATCHER_RECOVERY_DATABASE_URL` in a private override environment file
to this new database, then run the recovery profile with that environment:

```sh
docker compose --env-file .env --env-file /private/recovery.env --profile recovery run --rm recovery restore /backups/dispatcher.dump
```

Recovery checks the checksum and exact schema version before changing the target.
It refuses an existing application database. It creates the schema with its normal
migrations and restores data transactionally using an operator superuser. Public
database connection permission is removed during recovery. Only after successful
restoration and credential invalidation are runtime roles allowed to connect.
Do not point the API or worker at the new database until the command succeeds.

Recovered sessions, email links, OAuth flows and invitations are invalidated, and
all restored SDK/gateway keys are revoked. Sign in again and issue new application
credentials. PostgreSQL role OIDs/passwords are cluster-local: analytics mappings are
excluded, so reprovision each AgentData read-only credential with `dispatcher
analytics-access --tenant TENANT_UUID --new-login`. This creates a new cluster login
and invalidates older analytics mappings in the restored database without changing
another database's role/password. Use `--new-login` again for subsequent replacement.
Runtime database login
passwords remain operator-managed; run the normal migration/provisioning job with
the restored database's DSNs and chosen secrets before starting API/worker services.

Verify two tenants' historical totals and access separation before switching traffic.
If a restore fails, keep that database offline and retry into another new empty
database; the command never drops or overwrites a target. Apply later application
migrations only after restoring with the matching release.

`tests/test_recovery.py` creates two disposable databases, writes separate tenant
charges, dumps/restores them and checks non-bypass runtime access, exact costs,
revocation, checksum/schema checks and refusal to overwrite. It removes only its own
fixture databases. CI also builds the optional backup image against real PostgreSQL.
