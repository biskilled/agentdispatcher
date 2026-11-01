# AgentDesk identity and session attribution

Dispatcher uses its existing tenant memberships and app grants. AgentDesk proves the
caller's live identity; it cannot provision a Dispatcher member or merge accounts by
email. Remote roles may reduce local permissions, never increase them. AgentDesk's
project grants are not copied into Dispatcher: the owner explicitly manages app views
in Dispatcher. Telemetry project/work-item tags do not grant access to either product.

## Install the identity endpoint

`integration.patch` adds `GET /auth/dispatcher-identity` to AgentDesk. The endpoint calls
AgentDesk's real JWT verifier, then checks the current user's tenant, approved status,
active status and role in PostgreSQL. It rejects integration keys and development/open
authentication modes and fails closed when the database is unavailable. It returns no
email, password, token or prompt content.

Apply the patch to your AgentDesk checkout after reviewing it. For a newer checkout,
generate a fresh patch with `prepare_patch.py --agentdesk PATH --output PATCH_PATH`.
Run `verify_identity.py --agentdesk PATH` with AgentDesk's Python environment to verify
valid/invalid signatures, expiration, inactive members and unavailable dependencies.
The fixture uses AgentDesk's actual JWT code and an isolated in-memory user-store double;
it does not read or modify production users. Deploying the endpoint is a separate step.

Set `DISPATCHER_AGENTDESK_IDENTITY_URL` to the deployed endpoint's complete HTTPS URL.
This is operator configuration; callers cannot supply identity-server URLs. Redirects
are rejected. Changing the endpoint invalidates existing bindings until reconnected.

In the React **AgentDesk** section:

1. Sign in recently as a Dispatcher workspace owner. Connect the tenant using an
   administrator's AgentDesk human access token. One AgentDesk tenant binds to one
   Dispatcher tenant for this identity endpoint.
2. Each existing Dispatcher member explicitly links their own AgentDesk account.
3. Read `GET /api/agentdesk/usage` or `GET /api/agentdesk/sessions/{session_id}` with an
   AgentDesk `Authorization: Bearer …` header and the selected `X-Tenant-ID`.

Each read revalidates AgentDesk identity and local membership. Unlinking, disconnecting,
member removal and disabling the remote user stop subsequent reads. Tokens are used in
memory for the verification request and never saved. These routes do not mint browser
sessions. AgentDesk's existing JWT lifetime still applies: closing/logging out its
browser alone does not revoke an already issued JWT; disable the user or unlink the
Dispatcher account to revoke this connection immediately. Dispatcher browser sessions
retain their separate immediate logout/revocation behavior.

## Scheduled jobs and mid-session changes

Use the Python SDK's `context(project=…, work_item=…, pipeline_role=…, session_id=…)`
around each request or task. Context is copied into each attempt before it enters the
export queue. For queue workers, put `monitor.export_context()` into the job envelope
and restore with `monitor.context(**envelope_context)` in the worker. Never place keys
or user delegation tokens in that envelope. Use app/env-specific SDK keys for scheduled
services; these cannot read dashboards or manage account links.

For a caller session whose default task changes, call
`monitor.session_context(session_id, work_item=…, pipeline_role=…, effective_at=…)`.
This queues an immutable, effective-time snapshot before later usage. The intake route
is `/api/sessions/context`, protected by the same scoped SDK authentication. Duplicate
exports are idempotent; conflicting changes at the same timestamp are rejected.
The ledger fills only fields absent from the original event, using the snapshot active
at the event time. Explicit per-request fields (including null to clear a field) win.

Late-arriving context never rewrites already accepted attempts. When ordering across
multiple exporters cannot be guaranteed, send the context on each event instead.
Retries preserve the original evidence hash even if a later context snapshot arrives.
Group/filter by `work_item`, `pipeline_role`, `session_id`, or `job_run_id` to reconcile
the same attempts and costs between the browser and AgentDesk's authorized reads.

The integration tests exercise a real SDK scheduled job through HTTP intake, PostgreSQL,
the dashboard read model and AgentDesk-authenticated reads. They verify a mid-session
role/work-item switch, late telemetry, conflicting replay, scope denial and revocation.
Remote identity HTTP responses are isolated fixtures in those tests. Production Google,
SMTP and AgentDesk connection checks still require deployment credentials/configuration.
