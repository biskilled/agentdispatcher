# AgentData analytics connection

Run migrations before provisioning. The deployment operator supplies
`DISPATCHER_MIGRATION_DATABASE_URL` and a random `DISPATCHER_ANALYTICS_PASSWORD`
of at least 32 characters through the secret store, then runs:

```sh
dispatcher analytics-access --tenant TENANT_UUID
```

The command prints the login role name, never its password. Configure an AgentData
PostgreSQL connection with this role and password, pointing at the Dispatcher
database. Each tenant needs a separate connection credential. Import the accompanying
`llm_usage.yaml` Cube model or discover the `public.llm_usage` view through AgentData's
normal PostgreSQL discovery. The model follows AgentData's Cube export format; a live
AgentData import and monitoring of AgentData's own LLM calls remain to be verified.

Access is bound to PostgreSQL `session_user`, independently of generated SQL filters,
session settings and `SET ROLE`. Both the view and underlying ledger enforce this
binding. The credential cannot read identities, sessions, SDK secrets or change data.
It grants tenant-wide analytics and therefore belongs only in an authorised tenant
analytics connection, not a restricted member's browser. PostgreSQL 15+ is required.

Rerun provisioning with a new password to rotate the credential. To remove access,
including reads from existing pooled connections in subsequent transactions:

```sh
dispatcher analytics-access --tenant TENANT_UUID --revoke
```

Example questions and equivalent SQL (also checked against dashboard results):

```sql
-- How many attempts and input tokens did this workspace use?
SELECT count(*) AS attempts, sum(input_tokens) AS input_tokens FROM llm_usage;
-- What usage cost is known, separated by currency and evidence?
SELECT currency, cost_kind, sum(cost) FROM llm_usage GROUP BY currency, cost_kind;
-- Which providers account for the calls?
SELECT provider, count(*) FROM llm_usage GROUP BY provider;
```

These are request costs, excluding separate subscription fees, refunds and invoice
comparisons. NULL cost means unknown. Group monetary measures by currency and
cost_kind; calculated and app-reported estimates are not provider invoices.
Attempts include retries; distinct operation IDs count logical work. Joining jobs
or invoices must not multiply attempt rows. Reported user IDs are attribution,
while `verified_user_id` identifies server-validated user delegation.
