import { useRef, useState, type FormEvent } from "react";
import { api, apiResponse, money, type Overview, type Usage } from "./api";

const dimensions = [
  "app",
  "provider",
  "model",
  "source",
  "user_id",
  "environment",
  "trace_id",
  "session_id",
  "project",
  "work_item",
  "pipeline_role",
  "feature",
  "requested_model",
  "policy_version",
  "job_run_id",
  "config_version",
  "api_id",
];
const labels: Record<string, string> = {
  app_name: "Application",
  user_id: "Person / user ID",
  session_id: "Session ID",
  trace_id: "Trace ID",
  work_item: "Work item",
  pipeline_role: "Pipeline role",
  job_run_id: "Job run ID",
  config_version: "Config version",
  api_id: "API ID",
};
const label = (field: string) => labels[field] || field.replaceAll("_", " ");

/** Apply one filter set to totals, charts and the paginated attempt table. */
export function UsageControls({ apply }: { apply: (query: string) => void }) {
  const form = useRef<HTMLFormElement>(null);
  const [groupBy, setGroupBy] = useState("app");
  function applyForm(target: HTMLFormElement, group = groupBy) {
    const params = new URLSearchParams();
    for (const [key, value] of new FormData(target)) {
      if (typeof value === "string" && value)
        params.set(
          key,
          ["from_time", "to_time"].includes(key)
            ? new Date(value).toISOString()
            : value,
        );
    }
    params.set("group_by", group);
    setGroupBy(group);
    apply(params.toString());
  }
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    applyForm(event.currentTarget);
  }
  function fields(names: string[]) {
    return names.map((field) => (
      <label key={field}>
        {label(field)}
        <input name={field} />
      </label>
    ));
  }
  return (
    <>
      <div className="inline-form" role="group" aria-label="Usage views">
        {[
          { id: "app", name: "By application" },
          { id: "source", name: "By CLI / source" },
          { id: "user_id", name: "By person" },
        ].map((item) => (
          <button
            key={item.id}
            className={groupBy === item.id ? "primary" : "secondary"}
            onClick={() => {
              if (form.current) applyForm(form.current, item.id);
            }}
          >
            {item.name}
          </button>
        ))}
      </div>
      {groupBy === "user_id" && (
        <p>
          People are identified by the calling app. App-reported IDs are not
          verified identities; open a request's details to see its attribution.
          Unattributed usage includes background services. Shared provider keys
          cannot identify a person on their own.
        </p>
      )}
      <details className="panel form-panel">
        <summary>Filter and group usage</summary>
        <form ref={form} className="catalog-form" onSubmit={submit}>
          <label>
            From (local time)
            <input name="from_time" type="datetime-local" />
          </label>
          <label>
            Until (local time)
            <input name="to_time" type="datetime-local" />
          </label>
          {fields(["app_name", "source", "provider", "model", "user_id"])}
          <details className="advanced-filters">
            <summary>Advanced filters</summary>
            {fields(
              dimensions.filter(
                (field) =>
                  !["app", "source", "provider", "model", "user_id"].includes(
                    field,
                  ),
              ),
            )}
          </details>
          <label>
            Group by
            <select
              name="group_by"
              value={groupBy}
              onChange={(event) => setGroupBy(event.target.value)}
            >
              {dimensions.map((d) => (
                <option key={d} value={d}>
                  {d.replaceAll("_", " ")}
                </option>
              ))}
            </select>
          </label>
          <button className="primary">Apply filters</button>
          <button
            className="secondary"
            type="reset"
            onClick={() => {
              setGroupBy("app");
              apply("");
            }}
          >
            Clear filters
          </button>
        </form>
      </details>
    </>
  );
}

/** Download the selected visible attempts; the backend rejects oversized exports explicitly. */
export function UsageExport({
  tenant,
  query,
  report,
}: {
  tenant: string;
  query: string;
  report: (message: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  async function download() {
    setBusy(true);
    try {
      const response = await apiResponse(`/export/events?${query}`, tenant);
      const url = URL.createObjectURL(await response.blob());
      const link = document.createElement("a");
      link.href = url;
      link.download = "dispatcher-usage.json";
      link.click();
      URL.revokeObjectURL(url);
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <button className="secondary" disabled={busy} onClick={download}>
      {busy ? "Preparing export…" : "Export selected usage"}
    </button>
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
              {row.attempts} calls · {money(row.cost, row.currency)} ·{" "}
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
                <th>Input tokens</th>
                <th>Output tokens</th>
                <th>Cost</th>
              </tr>
            </thead>
            <tbody>
              {overview.groups.map((row, i) => (
                <tr key={i}>
                  <td>{row.label || "Unattributed"}</td>
                  <td>{row.attempts}</td>
                  <td>
                    {row.input_tokens == null
                      ? "Unknown"
                      : Number(row.input_tokens).toLocaleString()}
                  </td>
                  <td>
                    {row.output_tokens == null
                      ? "Unknown"
                      : Number(row.output_tokens).toLocaleString()}
                  </td>
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
