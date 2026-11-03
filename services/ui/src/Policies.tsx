import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

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
type Version = { revision: number; action: string; created_at: string };
type Props = {
  tenant: string;
  report: (message: string) => void;
};
const csv = (value: FormDataEntryValue | null) =>
  String(value || "")
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean);

/** Model aliases and capability requirements remain installation-specific configuration. */
export function PoliciesView({ tenant, report }: Props) {
  const [policies, setPolicies] = useState<Policy[]>([]);
  const [selected, setSelected] = useState("");
  const [history, setHistory] = useState<Version[]>([]);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  const policy = policies.find((row) => row.id === selected);
  useEffect(() => {
    let active = true;
    api<Policy[]>("/policies", tenant)
      .then((value) => {
        if (active) setPolicies(value);
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
        // Preserve any existing assignment managed through the API.
        experiment_id: policy?.config.experiment_id || null,
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
  return (
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
  );
}
