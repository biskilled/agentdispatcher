import { useState, type FormEvent } from "react";
import { api, money, type Overview, type Usage } from "./api";

const dimensions = [
  "app",
  "provider",
  "model",
  "source",
  "user_id",
  "environment",
  "session_id",
  "project",
  "work_item",
  "job_run_id",
  "config_version",
  "api_id",
];
const labels: Record<string, string> = {
  app_name: "Application",
  user_id: "User ID",
  session_id: "Session ID",
  work_item: "Work item",
  job_run_id: "Job run ID",
  config_version: "Config version",
  api_id: "API ID",
};
const label = (field: string) => labels[field] || field.replaceAll("_", " ");

/** Apply one filter set to totals, charts and the paginated attempt table. */
export function UsageControls({ apply }: { apply: (query: string) => void }) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(event.currentTarget)) {
      if (typeof value === "string" && value)
        params.set(
          key,
          ["from_time", "to_time"].includes(key)
            ? new Date(value).toISOString()
            : value,
        );
    }
    apply(params.toString());
  }
  return (
    <details className="panel form-panel">
      <summary>Filter and group usage</summary>
      <form className="catalog-form" onSubmit={submit}>
        <label>
          From (local time)
          <input name="from_time" type="datetime-local" />
        </label>
        <label>
          Until (local time)
          <input name="to_time" type="datetime-local" />
        </label>
        {dimensions
          .filter((d) => d !== "app")
          .concat("app_name")
          .map((field) => (
            <label key={field}>
              {label(field)}
              <input name={field} />
            </label>
          ))}
        <label>
          Group by
          <select name="group_by">
            {dimensions.map((d) => (
              <option key={d} value={d}>
                {d.replaceAll("_", " ")}
              </option>
            ))}
          </select>
        </label>
        <button className="primary">Apply filters</button>
        <button className="secondary" type="reset" onClick={() => apply("")}>
          Clear filters
        </button>
      </form>
    </details>
  );
}

/** Keep currencies/provenance separate while showing trend and selected dimension totals. */
export function UsageCharts({ overview }: { overview: Overview }) {
  const max = Math.max(1, ...overview.trend.map((row) => row.attempts));
  return (
    <div className="overview-grid">
      <section className="panel form-panel">
        <h2>Daily activity (UTC)</h2>
        <p>
          Up to {overview.chart_row_limit} daily currency/category rows. Totals
          include the full selected period.
        </p>
        {[...overview.trend].reverse().map((row, i) => (
          <div className="breakdown" key={i}>
            <span>{row.day.slice(0, 10)}</span>
            <div className="bar" aria-hidden="true">
              <span style={{ width: `${(row.attempts / max) * 100}%` }} />
            </div>
            <span>
              {row.attempts} calls · {money(row.cost, row.currency)}
              <small>
                {row.cost_kind} · {row.unknown_cost} unpriced
              </small>
            </span>
          </div>
        ))}
      </section>
      <section className="panel form-panel">
        <h2>Selected breakdown</h2>
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Dimension</th>
                <th>Attempts</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {overview.groups.map((row, i) => (
                <tr key={i}>
                  <td>{row.label || "Unattributed"}</td>
                  <td>{row.attempts}</td>
                  <td>
                    {money(row.cost, row.currency)}
                    <small>{row.cost_kind}</small>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

/** Fetch current authorization before displaying an attempt's original accounting evidence. */
export function AttemptDetail({
  tenant,
  eventId,
}: {
  tenant: string;
  eventId: string;
}) {
  const [event, setEvent] = useState<Usage | null>(null);
  const [error, setError] = useState("");
  async function open() {
    try {
      setEvent(await api<Usage>(`/events/${eventId}`, tenant));
      setError("");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <>
      <button className="secondary" onClick={open}>
        Details
      </button>
      {error && <p role="status">{error}</p>}
      {event && (
        <div
          className="attempt-detail"
          role="region"
          aria-label="Attempt details"
        >
          <button onClick={() => setEvent(null)}>Close details</button>
          <dl>
            <dt>User attribution</dt>
            <dd>{event.user_attribution}</dd>
            <dt>Verified user</dt>
            <dd>{event.verified_user_id || "None"}</dd>
            <dt>Price version</dt>
            <dd>{event.plan_id || "Unpriced"}</dd>
            {Object.entries(event.payload)
              .filter(([, v]) => v !== null)
              .map(([key, value]) => (
                <div key={key}>
                  <dt>{key.replaceAll("_", " ")}</dt>
                  <dd>{String(value)}</dd>
                </div>
              ))}
          </dl>
        </div>
      )}
    </>
  );
}
