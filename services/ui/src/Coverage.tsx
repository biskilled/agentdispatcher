import React, { useEffect, useState } from "react";
import { api } from "./api";

type Source = {
  app: string;
  environment: string;
  source: string;
  attempts: number;
  unknown_cost: number;
  last_seen: string;
};
type Reference = {
  app: string;
  environment: string;
  source: string;
  expected_source: string;
  correlation_kind: string;
  observations: number;
  matched: number;
  missing: number;
};
type Coverage = {
  adapters: {
    service_id: string;
    app: string;
    environment: string;
    source: string;
    accepted_exports: number;
    rejected_exports: number;
    stale: boolean;
    last_error: string | null;
  }[];
  sources: Source[];
  references: Reference[];
  coverage: string;
  row_limit: number;
};

export function CoverageView({
  tenant,
  report,
}: {
  tenant: string;
  report: (message: string) => void;
}) {
  const [data, setData] = useState<Coverage | null>(null);
  useEffect(() => {
    let active = true;
    api<Coverage>("/coverage", tenant)
      .then((value) => {
        if (active) setData(value);
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant]);
  return (
    <>
      <section className="panel form-panel">
        <h2>Reporting sources</h2>
        <p>{data?.coverage ?? "Loading source coverage…"}</p>
        {data && !data.sources.length && (
          <p>No billable-attempt evidence received yet.</p>
        )}
        {!!data?.sources.length && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Application</th>
                  <th>Environment</th>
                  <th>Source</th>
                  <th>Attempts</th>
                  <th>Unknown cost</th>
                  <th>Last report</th>
                </tr>
              </thead>
              <tbody>
                {data.sources.map((row) => (
                  <tr key={`${row.app}:${row.environment}:${row.source}`}>
                    <td>{row.app}</td>
                    <td>{row.environment}</td>
                    <td>{row.source}</td>
                    <td>{row.attempts}</td>
                    <td>{row.unknown_cost}</td>
                    <td>{new Date(row.last_seen).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
      {!!data?.adapters.length && (
        <section className="panel form-panel">
          <h2>Telemetry delivery</h2>
          <p>
            Export counts include replays. They are separate from unique
            billable attempts. Telemetry reports usage; it does not control
            model routing.
          </p>
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Application</th>
                  <th>Environment</th>
                  <th>Adapter</th>
                  <th>Accepted</th>
                  <th>Rejected</th>
                  <th>Delivery status</th>
                </tr>
              </thead>
              <tbody>
                {data.adapters.map((row) => (
                  <tr key={`${row.service_id}:${row.source}`}>
                    <td>{row.app}</td>
                    <td>{row.environment}</td>
                    <td>{row.source}</td>
                    <td>{row.accepted_exports}</td>
                    <td>{row.rejected_exports}</td>
                    <td>
                      {row.stale
                        ? "No recent exports"
                        : row.last_error
                          ? "Some usage was rejected"
                          : "Receiving exports"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="panel form-panel">
        <h2>Correlated observations</h2>
        <p>
          Client and transport observations link to the source that measures
          billable attempts. Their costs are never added a second time. Each
          upstream retry remains a separate attempt.
        </p>
        <p className="muted">
          Missing evidence may still be in transit, unavailable, or rejected
          before a provider call. It does not mean zero cost.
        </p>
        {data && !data.references.length && (
          <p>No overlapping source observations received yet.</p>
        )}
        {!!data?.references.length && (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Application</th>
                  <th>Environment</th>
                  <th>Observer</th>
                  <th>Expected source</th>
                  <th>Link</th>
                  <th>Matched</th>
                  <th>Missing</th>
                </tr>
              </thead>
              <tbody>
                {data.references.map((row) => (
                  <tr
                    key={`${row.app}:${row.environment}:${row.source}:${row.expected_source}:${row.correlation_kind}`}
                  >
                    <td>{row.app}</td>
                    <td>{row.environment}</td>
                    <td>{row.source}</td>
                    <td>{row.expected_source}</td>
                    <td>{row.correlation_kind}</td>
                    <td>
                      {row.matched} / {row.observations}
                    </td>
                    <td>{row.missing}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {data && (
          <p className="muted">Showing up to {data.row_limit} source groups.</p>
        )}
      </section>
    </>
  );
}
