import { useEffect, useState } from "react";
import { api } from "./api";

type Snapshot = {
  service_id: string;
  app: string;
  environment: string;
  received_at: string;
  stale: boolean;
  snapshot: {
    provider: string;
    account: string;
    status: string;
    observed_at: string | null;
    credits_remaining: number | null;
    spend: {
      used: number | null;
      limit: number | null;
      unit: string | null;
      period: string | null;
      balance: number | null;
      personal_used: number | null;
    } | null;
    windows: {
      label: string;
      used_percent: number | null;
      resets_at: string | null;
      reset_description: string | null;
      quota_limit: number | null;
      quota_unit: string | null;
    }[];
    details: {
      label: string;
      value: string | null;
      secondary_value: string | null;
    }[];
  };
};

/** Render the same CodexBar account snapshot contract for every reported provider. */
export function AccountUsage({
  tenant,
  query = "",
  revision,
}: {
  tenant: string;
  query?: string;
  revision: number;
}) {
  const [rows, setRows] = useState<Snapshot[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    let active = true;
    setRows([]);
    setError("");
    setLoading(true);
    api<Snapshot[]>(`/accounts?${query}`, tenant)
      .then((value) => {
        if (active) setRows(value);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [tenant, query, revision]);
  return (
    <section className="panel form-panel account-usage">
      <h2>CLI account limits &amp; balances</h2>
      <p>
        Latest account snapshots from CodexBar. These percentages and balances
        are separate from request costs above. The date range applies to request
        history.
      </p>
      {error && <p role="alert">{error}</p>}
      {loading && <p role="status">Loading account usage…</p>}
      {!loading && !rows.length && !error && (
        <p>
          No matching accounts have reported yet. Connect a device under Sources
          → CLI account usage.
        </p>
      )}
      <div className="account-grid">
        {rows.map(({ snapshot, ...row }) => (
          <article
            className="account-card"
            key={`${row.service_id}:${snapshot.provider}:${snapshot.account}`}
          >
            <div className="section-heading">
              <h3>{snapshot.provider}</h3>
              <span>
                {snapshot.status !== "ready"
                  ? "Unavailable"
                  : row.stale
                    ? "Stale"
                    : "Reported"}
              </span>
            </div>
            <p>
              {snapshot.account} · {row.app}
            </p>
            {snapshot.status === "error" && (
              <p>
                CodexBar could not refresh this account. Check authentication on
                the connected device.
              </p>
            )}
            {snapshot.windows.map((window, index) => (
              <div className="account-window" key={index}>
                <div>
                  <strong>{window.label}</strong>
                  <span>
                    {window.used_percent == null
                      ? "Usage unknown"
                      : `${window.used_percent}% used`}
                  </span>
                </div>
                {window.used_percent != null && (
                  <progress
                    max={100}
                    value={Math.max(0, Math.min(100, window.used_percent))}
                    aria-label={`${snapshot.provider} ${window.label} usage`}
                  />
                )}
                <small>
                  {window.resets_at
                    ? `Resets ${new Date(window.resets_at).toLocaleString()}`
                    : window.reset_description || "Reset time not reported"}
                </small>
                {window.quota_limit != null && (
                  <small>
                    Allowance: {window.quota_limit} {window.quota_unit}
                  </small>
                )}
              </div>
            ))}
            {snapshot.credits_remaining != null && (
              <p>
                Credit balance: <strong>{snapshot.credits_remaining}</strong>{" "}
                <small>(provider units)</small>
              </p>
            )}
            {snapshot.spend && (
              <div>
                <p>
                  {snapshot.spend.period || "Provider period"} spend:{" "}
                  <strong>
                    {snapshot.spend.used ?? "Unknown"} {snapshot.spend.unit}
                  </strong>
                  {snapshot.spend.limit != null && (
                    <> / {snapshot.spend.limit} limit</>
                  )}
                </p>
                {snapshot.spend.balance != null && (
                  <p>
                    Prepaid balance: {snapshot.spend.balance}{" "}
                    {snapshot.spend.unit}
                  </p>
                )}
                {snapshot.spend.personal_used != null && (
                  <p>
                    This account's share: {snapshot.spend.personal_used}{" "}
                    {snapshot.spend.unit}
                  </p>
                )}
                <small>Provider-reported; not added to request costs.</small>
              </div>
            )}
            {!!snapshot.details.length && (
              <details>
                <summary>Provider details</summary>
                <dl>
                  {snapshot.details.map((detail, index) => (
                    <div key={index}>
                      <dt>{detail.label}</dt>
                      <dd>
                        {detail.value ?? "Unknown"} {detail.secondary_value}
                      </dd>
                    </div>
                  ))}
                </dl>
              </details>
            )}
            <small>
              Measured:{" "}
              {snapshot.observed_at
                ? new Date(snapshot.observed_at).toLocaleString()
                : "Not reported"}
            </small>
          </article>
        ))}
      </div>
    </section>
  );
}
