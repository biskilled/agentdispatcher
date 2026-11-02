import React, { useState } from "react";
import { api } from "./api";

export type ConfigurationStatus = {
  source_id: string;
  source_state: string;
  digest: string | null;
  checked_at: string | null;
  coverage: string;
  instances: {
    instance_id: string;
    digest: string;
    state: string;
    occurred_at: string;
  }[];
};

type Candidate = {
  experiment_id: string;
  variant: string;
  path: string;
  before: string;
  after: string;
  evidence: {
    evidence: string;
    experiment: { currency: string };
    variants: {
      variant: string;
      cost_per_success?: string;
      quality?: string;
      latency_ms?: string;
    }[];
  };
};

export function ConfigurationHealth({
  statuses,
}: {
  statuses: ConfigurationStatus[];
}) {
  return (
    <section className="panel form-panel">
      <h2>Loaded configuration</h2>
      <p>
        Each application instance reports the version it loaded. Missing or
        stale reports do not confirm deployment.
      </p>
      {!statuses.length && (
        <p className="muted">
          Connect a configuration source to monitor changes.
        </p>
      )}
      {statuses.map((source) => (
        <article key={source.source_id}>
          <h3>
            {source.source_id} · source {source.source_state}
          </h3>
          <p className="muted">
            Last scan:{" "}
            {source.checked_at
              ? new Date(source.checked_at).toLocaleString()
              : "Not scanned"}
          </p>
          {!source.instances.length ? (
            <p>No runtime version reported.</p>
          ) : (
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Instance</th>
                    <th>Loaded version</th>
                    <th>Status</th>
                    <th>Reported</th>
                  </tr>
                </thead>
                <tbody>
                  {source.instances.map((instance) => (
                    <tr key={instance.instance_id}>
                      <td>{instance.instance_id}</td>
                      <td>{instance.digest.slice(0, 12)}</td>
                      <td>{instance.state.replaceAll("_", " ")}</td>
                      <td>{new Date(instance.occurred_at).toLocaleString()}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {!!source.instances.length && (
            <p className="muted">Coverage includes reporting instances only.</p>
          )}
        </article>
      ))}
    </section>
  );
}

export function ConfigurationRecommendations({
  tenant,
  sourceId,
  writable,
  run,
  proposed,
}: {
  tenant: string;
  sourceId: string;
  writable: boolean;
  run: (task: () => Promise<void>) => Promise<void>;
  proposed: () => Promise<void>;
}) {
  const [result, setResult] = useState<{
    digest: string;
    suggestions: Candidate[];
  } | null>(null);
  return (
    <section className="form-panel">
      <h3>Evaluated alternatives</h3>
      <p>
        Compare compatible models using task quality, latency and complete task
        costs, including retries and evaluation.
      </p>
      <button
        className="secondary"
        type="button"
        onClick={() =>
          void run(async () => {
            setResult(
              await api(
                `/configurations/${encodeURIComponent(sourceId)}/recommendations`,
                tenant,
                { method: "POST" },
              ),
            );
          })
        }
      >
        Check evaluated alternatives
      </button>
      {result && !result.suggestions.length && (
        <p>No compatible alternative currently meets the evaluation gates.</p>
      )}
      {result?.suggestions.map((candidate) => {
        const score = candidate.evidence.variants.find(
          (item) => item.variant === candidate.variant,
        );
        return (
          <article
            key={`${candidate.experiment_id}:${candidate.path}:${candidate.variant}`}
          >
            <h4>
              {candidate.path}: {candidate.before} → {candidate.after}
            </h4>
            <p>
              Cost per successful task: {score?.cost_per_success ?? "Unknown"}{" "}
              {candidate.evidence.experiment.currency} · Quality:{" "}
              {score?.quality ?? "Unknown"} · Latency:{" "}
              {score?.latency_ms ?? "Unknown"} ms
            </p>
            <p className="muted">{candidate.evidence.evidence}</p>
            <button
              className="primary"
              type="button"
              disabled={!writable}
              onClick={() =>
                void run(async () => {
                  await api(
                    `/configurations/${encodeURIComponent(sourceId)}/recommendations/propose`,
                    tenant,
                    {
                      method: "POST",
                      body: JSON.stringify({
                        digest: result.digest,
                        experiment_id: candidate.experiment_id,
                        variant: candidate.variant,
                        path: candidate.path,
                      }),
                    },
                  );
                  await proposed();
                })
              }
            >
              Prepare evaluated review
            </button>
          </article>
        );
      })}
    </section>
  );
}
