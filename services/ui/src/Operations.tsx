import { useEffect, useState, type FormEvent } from "react";
import { api, money } from "./api";

type Props = {
  tenant: string;
  section: "Schedules" | "Budgets";
  report: (s: string) => void;
};
type Resource = {
  id: string;
  revision: number;
  config: Record<string, unknown>;
};
type Health = {
  schedule_id: string;
  name: string;
  app: string;
  scheduled_for: string;
  observed_runs: number;
  state: string;
};
type BudgetUsage = {
  id: string;
  known_amount: string;
  currency: string;
  limit: string;
  unknown_events: number;
  fixed_fees: string;
  adjustments: string;
};
type Reconciled = {
  id: string;
  pool: string;
  amount: string | null;
  currency: string | null;
  observed_amount: string | null;
  drift: string | null;
  stale: boolean;
  source_note: string;
};

/** Capture calendar resets consistently across schedules and monetary budget windows. */
function CalendarFields() {
  return (
    <>
      <label>
        Cadence
        <select name="kind">
          <option value="daily">Daily</option>
          <option value="monthly">Monthly</option>
          <option value="fixed">Fixed seconds</option>
        </select>
      </label>
      <label>
        Time zone
        <input name="timezone" defaultValue="UTC" required />
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
        Fixed interval seconds
        <input name="seconds" type="number" min="1" defaultValue="3600" />
      </label>
      <label>
        Fixed interval anchor
        <input name="anchor" type="datetime-local" />
      </label>
    </>
  );
}

function windowFrom(data: Record<string, string>) {
  return {
    kind: data.kind,
    timezone: data.timezone,
    reset_hour: Number(data.reset_hour),
    reset_day: Number(data.reset_day),
    ...(data.kind === "fixed"
      ? {
          seconds: Number(data.seconds),
          anchor: new Date(data.anchor).toISOString(),
        }
      : {}),
  };
}

/** Administrators observe external jobs and spending; these forms never run business tasks. */
export function OperationsView({ tenant, section, report }: Props) {
  const [resources, setResources] = useState<Resource[]>([]);
  const [health, setHealth] = useState<Health[]>([]);
  const [spend, setSpend] = useState<BudgetUsage[]>([]);
  const [statements, setStatements] = useState<Reconciled[]>([]);
  const [revision, setRevision] = useState(0);
  const isSchedule = section === "Schedules";
  const route = isSchedule ? "/schedules" : "/budgets";
  useEffect(() => {
    let active = true;
    const refresh = async () => {
      const configs = await api<Resource[]>(route, tenant);
      if (active) setResources(configs);
      if (isSchedule) {
        const rows = await api<Health[]>("/schedules/health", tenant);
        if (active) setHealth(rows);
      } else {
        const [budgets, snapshots] = await Promise.all([
          api<BudgetUsage[]>("/budgets/usage", tenant),
          api<Reconciled[]>("/reconciliation", tenant),
        ]);
        if (active) {
          setSpend(budgets);
          setStatements(snapshots);
        }
      }
    };
    refresh().catch((error) => {
      if (active) report(error.message);
    });
    return () => {
      active = false;
    };
  }, [tenant, route, isSchedule, revision, report]);
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = Object.fromEntries(
      new FormData(event.currentTarget),
    ) as Record<string, string>;
    try {
      const config = isSchedule
        ? {
            id: data.id,
            name: data.name,
            app: data.app,
            environment: data.environment,
            first_expected: new Date(data.first_expected).toISOString(),
            cadence: windowFrom(data),
            grace_seconds: Number(data.grace_seconds),
          }
        : {
            id: data.id,
            amount: data.amount,
            currency: data.currency,
            window: windowFrom(data),
            apps: data.apps
              ? data.apps
                  .split(",")
                  .map((s) => s.trim())
                  .filter(Boolean)
              : null,
            thresholds: data.thresholds.split(",").map(Number),
          };
      const existing = resources.find((r) => r.id === data.id);
      await api(route, tenant, {
        method: "PUT",
        body: JSON.stringify({ config, revision: existing?.revision || 0 }),
      });
      setRevision((r) => r + 1);
      report(`${section} configuration saved.`);
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function toggle(resource: Resource) {
    try {
      await api(route, tenant, {
        method: "PUT",
        body: JSON.stringify({
          config: { ...resource.config, enabled: !resource.config.enabled },
          revision: resource.revision,
        }),
      });
      setRevision((r) => r + 1);
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function record(event: FormEvent<HTMLFormElement>, target: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const body = Object.fromEntries(new FormData(form)) as Record<
      string,
      unknown
    >;
    for (const key of ["period_start", "period_end", "observed_at"]) {
      if (body[key]) body[key] = new Date(String(body[key])).toISOString();
    }
    try {
      await api(target, tenant, { method: "POST", body: JSON.stringify(body) });
      setRevision((r) => r + 1);
      form.reset();
      report("Evidence recorded without changing original request prices.");
    } catch (error) {
      report((error as Error).message);
    }
  }
  return (
    <>
      <section className="panel form-panel">
        <h2>
          {isSchedule
            ? "Register an expected job"
            : "Configure a spending budget"}
        </h2>
        <p>
          {isSchedule
            ? "First expected time must match a cadence boundary. Your application continues to own and run the scheduler."
            : "Budgets monitor known costs and corrections; unknown charges remain visible. Account fees are included only in workspace-wide budgets."}
        </p>
        <form className="catalog-form" onSubmit={save} key={section}>
          <label>
            Configuration ID
            <input name="id" required pattern="[a-zA-Z0-9_-]+" />
          </label>
          {isSchedule ? (
            <>
              <label>
                Job name
                <input name="name" required />
              </label>
              <label>
                Application
                <input name="app" required />
              </label>
              <label>
                Environment
                <input name="environment" required />
              </label>
              <label>
                First expected (local time)
                <input name="first_expected" type="datetime-local" required />
              </label>
              <label>
                Grace period seconds
                <input
                  name="grace_seconds"
                  type="number"
                  min="0"
                  defaultValue="300"
                />
              </label>
            </>
          ) : (
            <>
              <label>
                Budget amount
                <input
                  name="amount"
                  type="number"
                  step="any"
                  min="0.000001"
                  required
                />
              </label>
              <label>
                Currency
                <input
                  name="currency"
                  pattern="[A-Z]{3}"
                  defaultValue="USD"
                  required
                />
              </label>
              <label>
                Applications (optional)
                <input
                  name="apps"
                  placeholder="Comma-separated; empty covers the workspace"
                />
              </label>
              <label>
                Thresholds (%)
                <input name="thresholds" defaultValue="80,100" />
              </label>
            </>
          )}
          <CalendarFields />
          <button className="primary">Save configuration</button>
        </form>
        <p>
          Using an existing configuration ID updates its currently displayed
          revision.
        </p>
      </section>
      <section className="panel form-panel">
        <h2>Registered configurations</h2>
        {resources.map((r) => (
          <div className="inline-form" key={r.id}>
            <strong>{r.id}</strong>
            <span>
              Revision {r.revision} ·{" "}
              {r.config.enabled ? "Enabled" : "Disabled"}
            </span>
            <button className="secondary" onClick={() => toggle(r)}>
              {r.config.enabled ? "Disable" : "Enable"}
            </button>
          </div>
        ))}
      </section>
      {isSchedule ? (
        <section className="panel form-panel">
          <h2>Expected-run health</h2>
          <p>
            Missed states are provisional and reconcile when late run evidence
            arrives. Refresh after the worker checks the schedule.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Job</th>
                  <th>Expected</th>
                  <th>Runs</th>
                  <th>State</th>
                </tr>
              </thead>
              <tbody>
                {health.map((h) => (
                  <tr key={`${h.schedule_id}:${h.scheduled_for}`}>
                    <td>
                      {h.name}
                      <small>{h.app}</small>
                    </td>
                    <td>{new Date(h.scheduled_for).toLocaleString()}</td>
                    <td>{h.observed_runs}</td>
                    <td>{h.state}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      ) : (
        <>
          <section className="panel form-panel">
            <h2>Budget consumption</h2>
            {spend.map((s) => (
              <div key={s.id} className="inline-form">
                <strong>{s.id}</strong>
                <span>
                  {money(s.known_amount, s.currency)} /{" "}
                  {money(s.limit, s.currency)}
                </span>
                <span>{s.unknown_events} unknown charges</span>
                <span>
                  Includes {money(s.fixed_fees, s.currency)} fixed fees and{" "}
                  {money(s.adjustments, s.currency)} adjustments
                </span>
              </div>
            ))}
          </section>
          <section className="panel form-panel">
            <h2>Import provider statement</h2>
            <p>
              Statements are comparison evidence. They do not add to
              already-counted usage.
            </p>
            <form
              className="catalog-form"
              onSubmit={(e) => record(e, "/reconciliation")}
            >
              <label>
                Pool ID
                <input name="pool" required placeholder="API:scope:account" />
              </label>
              <label>
                Provider reference
                <input name="provider_ref" required />
              </label>
              <label>
                Statement period start
                <input name="period_start" type="datetime-local" required />
              </label>
              <label>
                Statement period end
                <input name="period_end" type="datetime-local" required />
              </label>
              <label>
                Observed at
                <input name="observed_at" type="datetime-local" required />
              </label>
              <label>
                Reported amount
                <input name="amount" type="number" step="any" required />
              </label>
              <label>
                Currency
                <input
                  name="currency"
                  pattern="[A-Z]{3}"
                  defaultValue="USD"
                  required
                />
              </label>
              <label>
                Source evidence note
                <input name="source_note" required />
              </label>
              <button className="primary">Import statement</button>
            </form>
            {statements.map((s) => (
              <div key={s.id} className="inline-form">
                <strong>{s.pool}</strong>
                <span>
                  Reported {money(s.amount, s.currency)} / observed{" "}
                  {money(s.observed_amount, s.currency)}
                </span>
                <span>
                  Difference {money(s.drift, s.currency)} ·{" "}
                  {s.stale ? "Stale evidence" : "Recent evidence"}
                </span>
                <span>{s.source_note}</span>
              </div>
            ))}
          </section>
          <section className="panel form-panel">
            <h2>Record a refund or correction</h2>
            <p>
              Use a negative amount for a refund. Original event costs remain
              unchanged.
            </p>
            <form
              className="catalog-form"
              onSubmit={(e) => record(e, "/adjustments")}
            >
              <label>
                Original event ID
                <input name="event_id" required />
              </label>
              <label>
                Signed amount
                <input name="amount" type="number" step="any" required />
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
                Evidence reference
                <input name="source_ref" required />
              </label>
              <label>
                Reason
                <input name="reason" required />
              </label>
              <button className="primary">Record correction</button>
            </form>
          </section>
        </>
      )}
      <button className="secondary" onClick={() => setRevision((r) => r + 1)}>
        Refresh monitoring
      </button>
    </>
  );
}
