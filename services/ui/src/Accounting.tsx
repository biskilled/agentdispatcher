import { useEffect, useState, type FormEvent } from "react";
import { api, money, type Plan } from "./api";

type Props = {
  tenant: string;
  plans: Plan[];
  refresh: () => void;
  report: (s: string) => void;
};
type Connection = {
  id: string;
  revision: number;
  config: {
    id: string;
    name: string;
    api_id: string;
    account_pool: string;
    operations: string[];
    enabled: boolean;
  };
};
type Quota = {
  pool: string;
  rule: string;
  window: string;
  units: string;
  limit: string;
  remaining: string;
  unknown_events: number;
  end: string;
};
type Fee = {
  pool: string;
  period_start: string;
  amount: string;
  currency: string;
};
type Alert = {
  id: string;
  kind: string;
  created_at: string;
  evidence: { pool: string; threshold: number };
};
type Audit = {
  id: string;
  resource: string;
  action: string;
  actor_id: string;
  created_at: string;
  before_value: unknown;
  after_value: unknown;
};

function QuotaFields({ index }: { index: number }) {
  const prefix = `quota${index}`;
  return (
    <fieldset
      className="catalog-form"
      data-quota={prefix}
      style={{ gridColumn: "1 / -1" }}
    >
      <legend>Quota rule {index + 1}</legend>
      <label>
        Rule name
        <input
          name={`${prefix}_name`}
          defaultValue={`quota${index + 1}`}
          required
        />
      </label>
      <label>
        Quota limit
        <input
          name={`${prefix}_limit`}
          type="number"
          step="any"
          min="0.000001"
        />
      </label>
      <label>
        Quota window
        <select name={`${prefix}_kind`}>
          <option value="rolling">Rolling seconds</option>
          <option value="daily">Daily</option>
          <option value="monthly">Monthly</option>
        </select>
      </label>
      <label>
        Rolling window seconds
        <input
          name={`${prefix}_seconds`}
          type="number"
          min="1"
          defaultValue="60"
        />
      </label>
      <label>
        Counted HTTP status codes
        <input name={`${prefix}_statuses`} defaultValue="200,429" />
      </label>
      <label>
        Quota units per reported unit
        <input
          name={`${prefix}_weight`}
          type="number"
          step="any"
          min="0"
          defaultValue="1"
        />
      </label>
      <label>
        Timeout quota units
        <input
          name={`${prefix}_timeout`}
          type="number"
          step="any"
          min="0"
          placeholder="Unknown"
        />
      </label>
      <label>
        Count cached responses
        <input name={`${prefix}_cached`} type="checkbox" />
      </label>
      <label>
        Alert thresholds (%)
        <input name={`${prefix}_thresholds`} defaultValue="80,100" />
      </label>
    </fieldset>
  );
}

/** Convert a form to declarative pricing; the server remains the authoritative validator. */
function planFromForm(form: HTMLFormElement) {
  const data = Object.fromEntries(new FormData(form)) as Record<string, string>;
  const window = (prefix: string) => ({
    kind: data[`${prefix}_kind`],
    timezone: data.timezone,
    ...(data[`${prefix}_kind`] === "rolling"
      ? { seconds: Number(data[`${prefix}_seconds`]) }
      : {}),
    reset_day: Number(data.reset_day || 1),
    reset_hour: Number(data.reset_hour || 0),
  });
  return {
    api_id: data.api_id,
    name: data.name,
    unit_name: data.unit_name,
    pricing: data.pricing,
    effective_at: new Date(data.effective_at).toISOString(),
    currency: data.currency,
    pool_scope: data.pool_scope,
    source_note: data.source_note,
    verified_at: data.verified_at
      ? new Date(data.verified_at).toISOString()
      : null,
    unit_price: ["per_unit", "subscription"].includes(data.pricing)
      ? data.unit_price
      : null,
    fixed_fee: data.fixed_fee || "0",
    included_units: data.included_units || "0",
    billing_window: data.billing_kind ? window("billing") : null,
    tiers: ["graduated", "volume"].includes(data.pricing)
      ? data.tiers
          .split("\n")
          .filter((s) => s.trim())
          .map((line) => {
            const [bound, price] = line.split(",").map((s) => s.trim());
            return { up_to: bound === "*" ? null : bound, unit_price: price };
          })
      : [],
    input_token_price:
      data.pricing === "per_token" ? data.input_token_price : null,
    output_token_price:
      data.pricing === "per_token" ? data.output_token_price : null,
    charge_statuses: data.charge_statuses.split(",").map(Number),
    charge_outcomes: data.charge_outcomes.trim()
      ? data.charge_outcomes.split(",").map((value) => value.trim())
      : null,
    quota_rules: Array.from(
      form.querySelectorAll<HTMLFieldSetElement>("fieldset[data-quota]"),
    )
      .map((element) => element.dataset.quota!)
      .filter((prefix) => data[`${prefix}_limit`])
      .map((prefix) => ({
        name: data[`${prefix}_name`],
        limit: data[`${prefix}_limit`],
        window: window(prefix),
        statuses: data[`${prefix}_statuses`].split(",").map(Number),
        unit_weight: data[`${prefix}_weight`] || "1",
        timeout_units: data[`${prefix}_timeout`] || null,
        count_cached: data[`${prefix}_cached`] === "on",
        thresholds: data[`${prefix}_thresholds`].split(",").map(Number),
      })),
  };
}

/** Custom APIs use the same versioned pricing and pooled counters as built-in adapters. */
export function CatalogView({ tenant, plans, refresh, report }: Props) {
  const [pricing, setPricing] = useState("unknown");
  const [preview, setPreview] = useState("");
  const [connections, setConnections] = useState<Connection[]>([]);
  const [selected, setSelected] = useState<Connection | null>(null);
  const [quotas, setQuotas] = useState<Quota[]>([]);
  const [fees, setFees] = useState<Fee[]>([]);
  const [alerts, setAlerts] = useState<Alert[]>([]);
  const [history, setHistory] = useState<Audit[]>([]);
  const [quotaCount, setQuotaCount] = useState(1);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Connection[]>("/connections", tenant),
      api<Quota[]>("/quotas", tenant),
      api<Fee[]>("/charges", tenant),
      api<Alert[]>("/alerts", tenant),
      api<Audit[]>("/catalog/history", tenant),
    ])
      .then(([c, q, f, a, h]) => {
        if (active) {
          setConnections(c);
          setQuotas(q);
          setFees(f);
          setAlerts(a);
          setHistory(h);
        }
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, plans, report]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const plan = planFromForm(form);
      const previewOnly =
        (event.nativeEvent as SubmitEvent).submitter?.getAttribute("value") ===
        "preview";
      if (previewOnly) {
        const fields = new FormData(form);
        const result = await api<{
          cost: string | null;
          currency: string;
          fixed_fee_per_period: string;
        }>("/plans/preview", tenant, {
          method: "POST",
          body: JSON.stringify({
            plan,
            previous_units: fields.get("previous_units") || "0",
            event: {
              event_id: crypto.randomUUID(),
              attempt_id: crypto.randomUUID(),
              operation_id: crypto.randomUUID(),
              occurred_at: new Date().toISOString(),
              app: "preview",
              environment: "synthetic",
              resource_kind: "api",
              source: "synthetic-preview",
              provider: "fixture",
              operation: "preview",
              status: "success",
              status_code: 200,
              duration_ms: "0",
              units: fields.get("preview_units") || "1",
              input_tokens: Number(fields.get("preview_input") || 0),
              output_tokens: Number(fields.get("preview_output") || 0),
            },
          }),
        });
        setPreview(
          `Synthetic successful request: ${money(result.cost, result.currency)} variable cost; ${money(result.fixed_fee_per_period, result.currency)} fixed fee per billing period.`,
        );
      } else {
        await api("/plans", tenant, {
          method: "POST",
          body: JSON.stringify(plan),
        });
        refresh();
        report(
          "Pricing version saved. Existing costs retain their original calculation.",
        );
      }
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function saveConnection(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(
      new FormData(event.currentTarget),
    ) as Record<string, string>;
    try {
      await api("/connections", tenant, {
        method: "PUT",
        body: JSON.stringify({
          revision: selected?.revision || 0,
          config: {
            id: data.id,
            api_id: data.api_id,
            name: data.name,
            account_pool: data.account_pool,
            operations: data.operations
              .split(",")
              .map((s) => s.trim())
              .filter(Boolean),
            enabled: data.enabled === "true",
          },
        }),
      });
      setSelected(null);
      setRevision((r) => r + 1);
      report("API connection saved.");
    } catch (error) {
      report((error as Error).message);
    }
  }
  const cumulative = ["subscription", "graduated", "volume"].includes(pricing);
  return (
    <>
      <section className="panel form-panel">
        <h2>API connections</h2>
        <p>
          Connections can share an account quota pool. Provider keys stay in
          your applications.
        </p>
        <label>
          Edit connection
          <select
            value={selected?.id || ""}
            onChange={(e) =>
              setSelected(
                connections.find((c) => c.id === e.target.value) || null,
              )
            }
          >
            <option value="">New connection</option>
            {connections.map((c) => (
              <option key={c.id} value={c.id}>
                {c.config.name}
              </option>
            ))}
          </select>
        </label>
        <form
          className="catalog-form"
          onSubmit={saveConnection}
          key={selected?.id || "new"}
        >
          <label>
            Connection ID
            <input
              name="id"
              required
              pattern="[a-zA-Z0-9_-]+"
              readOnly={!!selected}
              defaultValue={selected?.id}
            />
          </label>
          <label>
            API ID
            <input
              name="api_id"
              required
              pattern="[a-zA-Z0-9_-]+"
              defaultValue={selected?.config.api_id}
            />
          </label>
          <label>
            Connection name
            <input name="name" required defaultValue={selected?.config.name} />
          </label>
          <label>
            Account pool
            <input
              name="account_pool"
              required
              pattern="[a-zA-Z0-9_-]+"
              defaultValue={selected?.config.account_pool}
            />
          </label>
          <label>
            Allowed operations (comma-separated)
            <input
              name="operations"
              defaultValue={selected?.config.operations.join(", ")}
              placeholder="Empty allows any operation"
            />
          </label>
          <label>
            Enabled
            <select
              name="enabled"
              defaultValue={String(selected?.config.enabled ?? true)}
            >
              <option value="true">Yes</option>
              <option value="false">No</option>
            </select>
          </label>
          <button className="primary">Save connection</button>
        </form>
      </section>
      <section className="panel form-panel">
        <h2>Register an API or add a pricing version</h2>
        <p>
          Configured prices are estimates. Use the API ID and connection ID in
          your SDK calls.
        </p>
        <form className="catalog-form" onSubmit={save}>
          <label>
            API ID
            <input name="api_id" required pattern="[a-zA-Z0-9_-]+" />
          </label>
          <label>
            Name
            <input name="name" required />
          </label>
          <label>
            Effective from
            <input name="effective_at" type="datetime-local" required />
          </label>
          <label>
            Pricing
            <select
              name="pricing"
              value={pricing}
              onChange={(e) => {
                setPricing(e.target.value);
                setPreview("");
              }}
            >
              <option value="unknown">Unknown</option>
              <option value="free">Explicitly free</option>
              <option value="per_unit">Per unit</option>
              <option value="subscription">Subscription and overage</option>
              <option value="graduated">Graduated tiers</option>
              <option value="volume">Volume tiers</option>
              <option value="per_token">LLM tokens</option>
            </select>
          </label>
          <label>
            Price per unit / overage
            <input
              name="unit_price"
              type="number"
              step="any"
              min="0"
              disabled={!["per_unit", "subscription"].includes(pricing)}
              required={["per_unit", "subscription"].includes(pricing)}
            />
          </label>
          <label>
            Currency
            <input
              name="currency"
              defaultValue="USD"
              pattern="[A-Z]{3}"
              required
            />
          </label>
          <label>
            Unit definition
            <input
              name="unit_name"
              defaultValue="request"
              required
              maxLength={50}
            />
          </label>
          <label>
            Pool scope
            <select name="pool_scope">
              <option value="api">All API calls</option>
              <option value="connection">Connection</option>
              <option value="account">Shared account</option>
              <option value="endpoint">Operation</option>
            </select>
          </label>
          <label>
            Charged HTTP status codes
            <input name="charge_statuses" defaultValue="200" required />
          </label>
          <label>
            Billable outcomes without HTTP status (optional)
            <input name="charge_outcomes" placeholder="success,error" />
            <small>For MCP or SDK calls: success, error, timeout, cached. Leave blank when unknown.</small>
          </label>
          {pricing === "per_token" && (
            <>
              <label>
                Price per input token
                <input
                  name="input_token_price"
                  type="number"
                  step="any"
                  min="0"
                  required
                />
              </label>
              <label>
                Price per output token
                <input
                  name="output_token_price"
                  type="number"
                  step="any"
                  min="0"
                  required
                />
              </label>
            </>
          )}
          <label>
            Billing period
            <select name="billing_kind" required={cumulative}>
              <option value="">No cumulative period</option>
              <option value="daily">Daily</option>
              <option value="monthly">Monthly</option>
            </select>
          </label>
          {cumulative && (
            <>
              <label>
                Included units
                <input
                  name="included_units"
                  type="number"
                  step="any"
                  min="0"
                  defaultValue="0"
                />
              </label>
              <label>
                Fixed fee per period
                <input
                  name="fixed_fee"
                  type="number"
                  step="any"
                  min="0"
                  defaultValue="0"
                />
              </label>
            </>
          )}
          {["graduated", "volume"].includes(pricing) && (
            <label>
              Tier boundaries and prices
              <textarea
                name="tiers"
                required
                placeholder={"10, 0.10\n*, 0.05"}
              />
              <small>
                One boundary, price per line. Use * for the final unlimited
                tier.
              </small>
            </label>
          )}
          <label>
            Reset time zone
            <input name="timezone" defaultValue="UTC" required />
          </label>
          <label>
            Monthly reset day
            <input
              name="reset_day"
              type="number"
              min="1"
              max="28"
              defaultValue="1"
            />
          </label>
          <label>
            Reset hour
            <input
              name="reset_hour"
              type="number"
              min="0"
              max="23"
              defaultValue="0"
            />
          </label>
          {Array.from({ length: quotaCount }, (_, index) => (
            <QuotaFields key={index} index={index} />
          ))}
          <button
            type="button"
            className="secondary"
            onClick={() => setQuotaCount(quotaCount + 1)}
          >
            Add quota rule
          </button>
          {quotaCount > 0 && (
            <button
              type="button"
              className="secondary"
              onClick={() => setQuotaCount(quotaCount - 1)}
            >
              Remove last quota rule
            </button>
          )}
          <label>
            Pricing source
            <input
              name="source_note"
              required
              defaultValue="User configured; not invoice verified"
            />
          </label>
          <label>
            Terms last verified
            <input name="verified_at" type="datetime-local" />
          </label>
          <label>
            Synthetic request units
            <input
              name="preview_units"
              type="number"
              step="any"
              min="0"
              defaultValue="1"
            />
          </label>
          <label>
            Previously consumed units
            <input
              name="previous_units"
              type="number"
              step="any"
              min="0"
              defaultValue="0"
            />
          </label>
          {pricing === "per_token" && (
            <>
              <label>
                Synthetic input tokens
                <input
                  name="preview_input"
                  type="number"
                  min="0"
                  defaultValue="100"
                />
              </label>
              <label>
                Synthetic output tokens
                <input
                  name="preview_output"
                  type="number"
                  min="0"
                  defaultValue="20"
                />
              </label>
            </>
          )}
          <button className="secondary" value="preview">
            Preview price
          </button>
          <button className="primary" value="publish">
            Save pricing version
          </button>
        </form>
        {preview && (
          <p className="notice" role="status">
            {preview}
          </p>
        )}
      </section>
      <section className="panel form-panel">
        <h2>Observed quotas</h2>
        <p>
          Local estimates cover reported calls. Monitoring does not block
          requests or guarantee provider remaining balance.
        </p>
        {quotas.length ? (
          quotas.map((q) => (
            <div className="inline-form" key={`${q.pool}:${q.rule}`}>
              <strong>
                {q.pool} / {q.rule}
              </strong>
              <span>
                {q.units} / {q.limit} units · {q.remaining} locally remaining
              </span>
              <span>{q.unknown_events} attempts with unknown consumption</span>
              <span>
                {q.window} window ending {new Date(q.end).toLocaleString()}
              </span>
            </div>
          ))
        ) : (
          <p>No observed quota pools yet.</p>
        )}
      </section>
      <section className="panel form-panel">
        <h2>Fixed subscription charges</h2>
        <p>
          Recorded once per observed billing period, separately from variable
          request costs. Unobserved periods are not inferred.
        </p>
        {fees.map((f) => (
          <div className="inline-form" key={`${f.pool}:${f.period_start}`}>
            <strong>{f.pool}</strong>
            <span>{money(f.amount, f.currency)}</span>
            <span>{new Date(f.period_start).toLocaleDateString()}</span>
          </div>
        ))}
      </section>
      <section className="panel form-panel">
        <h2>Quota alerts</h2>
        {alerts.length ? (
          alerts.map((a) => (
            <p key={a.id}>
              {a.evidence.pool}: {a.evidence.threshold}% observed ·{" "}
              {new Date(a.created_at).toLocaleString()}
            </p>
          ))
        ) : (
          <p>No threshold notifications.</p>
        )}
      </section>
      <section className="panel form-panel">
        <h2>Pricing history</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>API</th>
                <th>Formula</th>
                <th>Effective from</th>
              </tr>
            </thead>
            <tbody>
              {plans.map((p) => (
                <tr key={p.id}>
                  <td>
                    <strong>{p.plan.name}</strong>
                    <small>{p.api_id}</small>
                  </td>
                  <td>{p.plan.pricing.replaceAll("_", " ")}</td>
                  <td>{new Date(p.effective_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
      <section className="panel form-panel">
        <h2>Configuration audit</h2>
        {history.map((entry) => (
          <details key={entry.id}>
            <summary>
              {entry.resource} · {entry.action} ·{" "}
              {new Date(entry.created_at).toLocaleString()}
            </summary>
            <p>Changed by {entry.actor_id}</p>
            <pre>
              {JSON.stringify(
                { before: entry.before_value, after: entry.after_value },
                null,
                2,
              )}
            </pre>
          </details>
        ))}
      </section>
    </>
  );
}
