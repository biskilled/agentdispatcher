import { useEffect, useState, type FormEvent } from "react";
import { api, money } from "./api";

type PolicyConfig = {
  id: string;
  app: string;
  environment: string;
  allowed_models: string[];
  primary: string | null;
  fallbacks: string[];
  required_capabilities: string[];
  model_capabilities: Record<string, string[]>;
  experiment_id: string | null;
};
type Policy = { id: string; revision: number; config: PolicyConfig };
type Experiment = {
  id: string;
  config: { name: string; app: string; environment: string };
};
type Version = { revision: number; action: string; created_at: string };
type VariantResult = {
  variant: string;
  model: string;
  assigned: number;
  completed?: number;
  attempts?: number;
  quality?: string;
  task_cost?: string;
  cost_per_success?: string | null;
  evaluation_cost?: string;
  eligible: boolean;
  reasons: string[];
};
type Results = {
  experiment: { id: string; currency: string };
  evidence: string;
  variants: VariantResult[];
};
type Props = {
  tenant: string;
  section: string;
  report: (message: string) => void;
};
const csv = (value: FormDataEntryValue | null) =>
  String(value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

/** Model aliases and capability requirements remain installation-specific configuration. */
export function PoliciesView({ tenant, section, report }: Props) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [experiments, setExperiments] = useState<Experiment[]>([]);
  const [selected, setSelected] = useState("");
  const [experimentId, setExperimentId] = useState("");
  const [history, setHistory] = useState<Version[]>([]);
  const [results, setResults] = useState<Results | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const policy = policies.find((row) => row.id === selected);
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Policy[]>("/policies", tenant),
      api<Experiment[]>("/experiments", tenant),
    ])
      .then(([p, e]) => {
        if (active) {
          setPolicies(p);
          setExperiments(e);
        }
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, report]);
  useEffect(() => {
    let active = true;
    setHistory([]);
    if (selected)
      api<Version[]>(
        `/policies/${encodeURIComponent(selected)}/history`,
        tenant,
      )
        .then((value) => {
          if (active) setHistory(value);
        })
        .catch((error) => {
          if (active) report(error.message);
        });
    return () => {
      active = false;
    };
  }, [tenant, selected, revision, report]);
  useEffect(() => {
    let active = true;
    setResults(null);
    if (experimentId)
      api<Results>(`/experiments/${experimentId}`, tenant)
        .then((value) => {
          if (active) setResults(value);
        })
        .catch((error) => {
          if (active) report(error.message);
        });
    return () => {
      active = false;
    };
  }, [tenant, experimentId, revision, report]);

  async function mutate(
    path: string,
    body: unknown,
    message: string,
    method = "POST",
  ) {
    setBusy(true);
    try {
      await api(path, tenant, { method, body: JSON.stringify(body) });
      setRevision((value) => value + 1);
      report(message);
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  function savePolicy(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      const config = {
        id: data.get("id"),
        app: data.get("app"),
        environment: data.get("environment"),
        allowed_models: csv(data.get("allowed_models")),
        primary: data.get("primary") || null,
        fallbacks: csv(data.get("fallbacks")),
        required_capabilities: csv(data.get("required_capabilities")),
        model_capabilities: JSON.parse(
          String(data.get("model_capabilities") || "{}"),
        ),
        experiment_id: data.get("experiment_id") || null,
      };
      void mutate(
        "/policies",
        { config, revision: policy?.revision || 0 },
        "Policy activated. New gateway requests use this revision.",
        "PUT",
      );
    } catch {
      report(
        "Capability declarations must be a JSON object of model aliases and capability lists.",
      );
    }
  }
  function createExperiment(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    void mutate(
      "/experiments",
      {
        name: data.get("name"),
        app: data.get("app"),
        environment: data.get("environment"),
        seed: crypto.randomUUID(),
        baseline: "baseline",
        currency: data.get("currency"),
        minimum_tasks: Number(data.get("minimum_tasks")),
        minimum_quality: data.get("minimum_quality"),
        quality_margin: data.get("quality_margin"),
        maximum_latency_ms: data.get("maximum_latency_ms"),
        configuration_source: data.get("configuration_source") || null,
        configuration_digest: data.get("configuration_digest") || null,
        variants: [
          { name: "baseline", model: data.get("baseline_model"), weight: 1 },
          { name: "candidate", model: data.get("candidate_model"), weight: 1 },
        ],
      },
      "Experiment created. Assign it to a compatible model policy to start routing tasks.",
    );
  }
  const promotingPolicy = policies.find(
    (row) => row.config.experiment_id === experimentId,
  );
  return section === "Model policies" ? (
    <>
      <section className="panel form-panel">
        <h2>Model routing policy</h2>
        <p>
          One policy applies to each application and environment. Every route
          must also be allowed by its LLM key. Capability declarations are
          supplied by your administrator.
        </p>
        <label>
          Policy to edit
          <select
            value={selected}
            onChange={(event) => setSelected(event.target.value)}
          >
            <option value="">Create a policy</option>
            {policies.map((row) => (
              <option key={row.id} value={row.id}>
                {row.id} · revision {row.revision}
              </option>
            ))}
          </select>
        </label>
        <form
          className="catalog-form"
          key={`${selected}-${policy?.revision || 0}`}
          onSubmit={savePolicy}
        >
          <label>
            Policy ID
            <input
              name="id"
              required
              defaultValue={policy?.config.id}
              readOnly={!!policy}
            />
          </label>
          <label>
            Application
            <input
              name="app"
              required
              defaultValue={policy?.config.app}
              readOnly={!!policy}
            />
          </label>
          <label>
            Environment
            <input
              name="environment"
              required
              defaultValue={policy?.config.environment}
              readOnly={!!policy}
            />
          </label>
          <label>
            Allowed model aliases (comma separated)
            <input
              name="allowed_models"
              required
              defaultValue={policy?.config.allowed_models.join(", ")}
            />
          </label>
          <label>
            Force primary alias (optional)
            <input name="primary" defaultValue={policy?.config.primary || ""} />
          </label>
          <label>
            Fallback aliases in order
            <input
              name="fallbacks"
              defaultValue={policy?.config.fallbacks.join(", ")}
            />
          </label>
          <label>
            Required capabilities (comma separated)
            <input
              name="required_capabilities"
              defaultValue={policy?.config.required_capabilities.join(", ")}
            />
          </label>
          <label>
            Model capability declarations (JSON)
            <textarea
              name="model_capabilities"
              rows={3}
              defaultValue={JSON.stringify(
                policy?.config.model_capabilities || {},
              )}
            />
          </label>
          <label>
            Active experiment
            <select
              name="experiment_id"
              defaultValue={policy?.config.experiment_id || ""}
            >
              <option value="">No experiment</option>
              {experiments.map((row) => (
                <option key={row.id} value={row.id}>
                  {row.config.name} · {row.config.app}/{row.config.environment}
                </option>
              ))}
            </select>
          </label>
          <button className="primary" disabled={busy}>
            Activate policy
          </button>
        </form>
      </section>
      {!!history.length && (
        <section className="panel form-panel">
          <h2>Routing history</h2>
          {history.map((row) => (
            <div className="connection-row" key={row.revision}>
              <p>
                Revision {row.revision}: {row.action} ·{" "}
                {new Date(row.created_at).toLocaleString()}
              </p>
              {row.revision !== policy?.revision && (
                <button
                  disabled={busy}
                  onClick={() =>
                    mutate(
                      `/policies/${encodeURIComponent(selected)}/rollback`,
                      {
                        revision: policy?.revision,
                        target_revision: row.revision,
                      },
                      "Previous routing restored as a new policy revision.",
                    )
                  }
                >
                  Restore revision {row.revision}
                </button>
              )}
            </div>
          ))}
        </section>
      )}
    </>
  ) : (
    <>
      <section className="panel form-panel">
        <h2>Compare model candidates</h2>
        <p>
          Assignments stay stable for a whole task. Quality feedback and
          complete cost coverage are required before promotion. Evaluation
          calls, failed attempts and declared fee allocations count toward cost.
        </p>
        <form className="catalog-form" onSubmit={createExperiment}>
          <label>
            Experiment name
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
            Baseline model alias
            <input name="baseline_model" required />
          </label>
          <label>
            Candidate model alias
            <input name="candidate_model" required />
          </label>
          <label>
            Currency
            <input
              name="currency"
              required
              pattern="[A-Z]{3}"
              defaultValue="USD"
            />
          </label>
          <label>
            Minimum tasks per variant
            <input
              name="minimum_tasks"
              type="number"
              min="2"
              defaultValue="30"
              required
            />
          </label>
          <label>
            Minimum quality (0–1)
            <input
              name="minimum_quality"
              type="number"
              min="0"
              max="1"
              step="0.01"
              defaultValue="0.9"
              required
            />
          </label>
          <label>
            Allowed quality difference from baseline
            <input
              name="quality_margin"
              type="number"
              min="0"
              max="1"
              step="0.01"
              defaultValue="0.05"
              required
            />
          </label>
          <label>
            Maximum average task latency (ms)
            <input name="maximum_latency_ms" type="number" min="1" required />
          </label>
          <label>
            Configuration source (optional)
            <input name="configuration_source" />
          </label>
          <label>
            Configuration SHA-256 (required with source)
            <input name="configuration_digest" pattern="[0-9a-f]{64}" />
          </label>
          <button className="primary" disabled={busy}>
            Create experiment
          </button>
        </form>
      </section>
      <section className="panel form-panel">
        <h2>Experiment results</h2>
        <label>
          Experiment
          <select
            value={experimentId}
            onChange={(event) => setExperimentId(event.target.value)}
          >
            <option value="">Select an experiment</option>
            {experiments.map((row) => (
              <option key={row.id} value={row.id}>
                {row.config.name}
              </option>
            ))}
          </select>
        </label>
        {results && (
          <>
            <p>{results.evidence}</p>
            {results.variants.map((row) => (
              <article className="notice" key={row.variant}>
                <h3>
                  {row.variant}: {row.model}
                </h3>
                <p>
                  {row.assigned} assigned tasks · {row.completed || 0} completed
                  · {row.attempts || 0} attempts
                </p>
                <p>
                  Quality: {row.quality ?? "Pending"} · Cost per successful
                  task:{" "}
                  {money(
                    row.cost_per_success ?? null,
                    results.experiment.currency,
                  )}
                </p>
                {row.reasons.length > 0 && (
                  <ul>
                    {row.reasons.map((reason) => (
                      <li key={reason}>{reason}</li>
                    ))}
                  </ul>
                )}
                {row.eligible && (
                  <>
                    <p>
                      This candidate meets your configured promotion gates.
                      Observations do not prove future savings or quality.
                    </p>
                    <button
                      disabled={busy || !promotingPolicy}
                      onClick={() =>
                        mutate(
                          `/experiments/${experimentId}/promote`,
                          {
                            variant: row.variant,
                            policy_id: promotingPolicy?.id,
                            revision: promotingPolicy?.revision,
                          },
                          "Candidate activated. Restore an earlier revision in Model policies to roll back.",
                        )
                      }
                    >
                      Promote {row.variant}
                    </button>
                  </>
                )}
              </article>
            ))}
          </>
        )}
      </section>
    </>
  );
}
