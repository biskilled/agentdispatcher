import { useEffect, useRef, useState, type FormEvent } from "react";
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
  app_name: "Application / device",
  source: "Tool / source",
  provider: "Provider",
  model: "Model",
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
export function UsageControls({
  apply,
  tenant,
  revision,
  query,
}: {
  apply: (query: string) => void;
  tenant: string;
  revision: number;
  query: string;
}) {
  const [options, setOptions] = useState<Record<string, string[]>>({});
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    api<Record<string, string[]>>("/usage/filter-options", tenant)
      .then((value) => {
        if (active) {
          setOptions(value);
          setError("");
        }
      })
      .catch(() => {
        if (active)
          setError(
            "Filter suggestions unavailable; you can still enter a value.",
          );
      });
    return () => {
      active = false;
    };
  }, [tenant, revision]);
  const form = useRef<HTMLFormElement>(null);
  const [groupBy, setGroupBy] = useState("app");
  useEffect(() => {
    const params = new URLSearchParams(query);
    setGroupBy(params.get("group_by") || "app");
    form.current
      ?.querySelectorAll<HTMLInputElement>("input[name]")
      .forEach((input) => {
        const value = params.get(input.name) || "";
        if (input.type === "checkbox") input.checked = value === "true";
        else if (input.type === "datetime-local" && value) {
          const date = new Date(value);
          input.value = new Date(
            date.getTime() - date.getTimezoneOffset() * 60000,
          )
            .toISOString()
            .slice(0, 16);
        } else input.value = value;
      });
  }, [query]);
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
        <input name={field} list={`usage-${field}`} placeholder="All" />
        <datalist id={`usage-${field}`}>
          {(options[field] || []).map((value) => (
            <option key={value} value={value} />
          ))}
        </datalist>
      </label>
    ));
  }
  return (
    <>
      <section
        className="panel form-panel usage-filters"
        aria-label="Usage filters"
      >
        <h2>Filter usage</h2>
        {error && <p role="status">{error}</p>}
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
          <label className="check-label">
            <input name="include_test" type="checkbox" value="true" />
            Include labeled test data
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
      </section>
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
