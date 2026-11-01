import React, { useEffect, useState } from "react";
import { api } from "./api";

type Field = {
  kind: string;
  models: string[];
  minimum: number | null;
  maximum: number | null;
};
type Scalar = string | number | boolean;
type Source = {
  id: string;
  app: string;
  environment: string;
  kind: string;
  writable: boolean;
  fields: Record<string, Field>;
};
type Version = {
  digest: string;
  revision: string;
  inventory: Record<string, Scalar>;
};
type Change = {
  id: string;
  source_id: string;
  state: string;
  result_revision: string | null;
  diff: { path: string; before: Scalar; after: Scalar }[];
};

export function ConfigurationsView({
  tenant,
  report,
}: {
  tenant: string;
  report: (message: string) => void;
}) {
  const [sources, setSources] = useState<Source[]>([]);
  const [sourceId, setSourceId] = useState("");
  const [version, setVersion] = useState<Version | null>(null);
  const [values, setValues] = useState<Record<string, Scalar>>({});
  const [changes, setChanges] = useState<Change[]>([]);
  const [busy, setBusy] = useState(false);
  const source = sources.find((item) => item.id === sourceId);

  async function history() {
    setChanges(await api<Change[]>("/configurations/changes", tenant));
  }
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Source[]>("/configurations", tenant),
      api<Change[]>("/configurations/changes", tenant),
    ])
      .then(([available, pending]) => {
        if (active) {
          setSources(available);
          setChanges(pending);
        }
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant]);

  async function action(task: () => Promise<void>) {
    setBusy(true);
    try {
      await task();
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function scan() {
    const current = await api<Version>(
      `/configurations/${encodeURIComponent(sourceId)}/scan`,
      tenant,
      { method: "POST" },
    );
    setVersion(current);
    setValues(current.inventory);
  }
  async function propose(event: React.FormEvent) {
    event.preventDefault();
    if (!version) return;
    await action(async () => {
      const edits = Object.fromEntries(
        Object.entries(values).filter(
          ([key, value]) => version.inventory[key] !== value,
        ),
      );
      if (!Object.keys(edits).length) {
        report("Change a permitted parameter before preparing a review.");
        return;
      }
      await api(
        `/configurations/${encodeURIComponent(sourceId)}/proposals`,
        tenant,
        {
          method: "POST",
          body: JSON.stringify({ digest: version.digest, changes: edits }),
        },
      );
      await history();
      report("Review the exact changes below before applying them.");
    });
  }
  async function transition(change: Change, operation: string) {
    await action(async () => {
      await api(`/configurations/changes/${change.id}/${operation}`, tenant, {
        method: "POST",
      });
      await history();
      setVersion(null);
      report(
        operation === "rollback"
          ? "Prior values restored. The application still needs to reload."
          : "Change saved. Check its activation state before treating it as deployed.",
      );
    });
  }
  return (
    <>
      <section className="panel form-panel">
        <h2>Application configuration</h2>
        <p>
          Review permitted model and parameter changes. Your app keeps its YAML,
          prompts and credentials.
        </p>
        {!sources.length ? (
          <p className="muted">
            No configuration sources are connected. Your installation
            administrator can grant access to an app configuration file, API or
            Git repository.
          </p>
        ) : (
          <>
            <div className="inline-form">
              <label>
                Configuration source
                <select
                  value={sourceId}
                  disabled={busy}
                  onChange={(event) => {
                    setSourceId(event.target.value);
                    setVersion(null);
                  }}
                >
                  <option value="">Select a source</option>
                  {sources.map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.app} / {item.environment} / {item.id}
                    </option>
                  ))}
                </select>
              </label>
              <button
                className="secondary"
                disabled={!source || busy}
                onClick={() => void action(scan)}
              >
                Scan current version
              </button>
            </div>
            {version && source && (
              <form onSubmit={propose}>
                <p className="muted">
                  Version {version.digest.slice(0, 12)} ·{" "}
                  {source.writable
                    ? "Reviewed changes permitted"
                    : "Read-only access"}
                </p>
                <div className="inline-form">
                  {Object.entries(source.fields).map(([name, field]) => (
                    <label key={name}>
                      {name}
                      {field.kind === "model" ? (
                        <select
                          value={String(values[name])}
                          disabled={!source.writable || busy}
                          onChange={(event) =>
                            setValues({ ...values, [name]: event.target.value })
                          }
                        >
                          {field.models.map((model) => (
                            <option key={model}>{model}</option>
                          ))}
                        </select>
                      ) : field.kind === "boolean" ? (
                        <input
                          type="checkbox"
                          checked={Boolean(values[name])}
                          disabled={!source.writable || busy}
                          onChange={(event) =>
                            setValues({
                              ...values,
                              [name]: event.target.checked,
                            })
                          }
                        />
                      ) : (
                        <input
                          type="number"
                          required
                          step={field.kind === "integer" ? "1" : "any"}
                          min={field.minimum ?? undefined}
                          max={field.maximum ?? undefined}
                          value={String(values[name])}
                          disabled={!source.writable || busy}
                          onChange={(event) =>
                            setValues({
                              ...values,
                              [name]: Number(event.target.value),
                            })
                          }
                        />
                      )}
                    </label>
                  ))}
                  {source.writable && (
                    <button className="primary" disabled={busy}>
                      Prepare review
                    </button>
                  )}
                </div>
              </form>
            )}
          </>
        )}
      </section>
      <section className="panel form-panel">
        <h2>Changes and activation</h2>
        <p>
          Saved changes remain pending until the application reports that it
          loaded the version.
        </p>
        {!changes.length && <p className="muted">No changes proposed yet.</p>}
        {changes.map((change) => (
          <article key={change.id}>
            <h3>
              {change.source_id} · {change.state.replaceAll("_", " ")}
            </h3>
            <div className="table-scroll">
              <table>
                <thead>
                  <tr>
                    <th>Parameter</th>
                    <th>Before</th>
                    <th>After</th>
                  </tr>
                </thead>
                <tbody>
                  {change.diff.map((item) => (
                    <tr key={item.path}>
                      <td>{item.path}</td>
                      <td>{String(item.before)}</td>
                      <td>{String(item.after)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {change.result_revision && (
              <p className="muted">Source revision: {change.result_revision}</p>
            )}
            {["proposed", "applying"].includes(change.state) && (
              <button
                className="primary"
                disabled={busy}
                onClick={() => void transition(change, "apply")}
              >
                Apply reviewed changes
              </button>
            )}
            {["awaiting_activation", "activated", "activation_failed"].includes(
              change.state,
            ) && (
              <button
                className="secondary"
                disabled={busy}
                onClick={() => void transition(change, "rollback")}
              >
                Restore previous values
              </button>
            )}
          </article>
        ))}
      </section>
    </>
  );
}
