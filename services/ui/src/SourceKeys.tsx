import { useState, type FormEvent } from "react";
import { KeyRound } from "lucide-react";
import { api, type Key } from "./api";
import { credentialSources, type CredentialSource } from "./sourceTypes";
import { GatewayRouting } from "./GatewayRouting";
import { GatewayModelPicker } from "./GatewayModelPicker";
import { type GatewayConnection } from "./gatewayConnection";

/** Manage scoped source credentials; editing cannot widen application or model access. */
export function SourceKeys({
  tenant,
  keys,
  refresh,
  report,
  source,
  gatewayConnection,
}: {
  tenant: string;
  keys: Key[];
  refresh: () => void;
  report: (s: string) => void;
  source: CredentialSource | "gateway";
  gatewayConnection?: GatewayConnection | null;
}) {
  const gateway = source === "gateway";
  const accountSync = source === "codexbar";
  const [editing, setEditing] = useState<Key | null>(null);
  const [routing, setRouting] = useState<Key | null>(null);
  const [busy, setBusy] = useState(false);
  const [secret, setSecret] = useState("");
  const [selectedModels, setSelectedModels] = useState<string[]>([]);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    if (gateway && !selectedModels.length) {
      report("Select at least one allowed model.");
      return;
    }
    setBusy(true);
    const form = event.currentTarget;
    const fields = Object.fromEntries(new FormData(form));
    const { models, ...scope } = fields;
    const data = gateway
      ? {
          ...scope,
          models: selectedModels,
        }
      : { ...scope, source_type: source };
    try {
      const result = await api<{ secret: string }>(
        gateway ? "/gateway/keys" : "/keys",
        tenant,
        {
          method: "POST",
          body: JSON.stringify(data),
        },
      );
      setSecret(result.secret);
      form.reset();
      setSelectedModels([]);
      refresh();
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!editing || busy) return;
    setBusy(true);
    try {
      await api(`/keys/${editing.id}`, tenant, {
        method: "PUT",
        body: JSON.stringify(
          Object.fromEntries(new FormData(event.currentTarget)),
        ),
      });
      setEditing(null);
      refresh();
      report("Connection updated.");
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    if (busy) return;
    setBusy(true);
    try {
      await api(`/keys/${id}`, tenant, { method: "DELETE" });
      setEditing(null);
      setSecret("");
      setRouting(null);
      refresh();
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      <section className="panel form-panel">
        <h2>{gateway ? "Add connection LLM key" : "Add connection"}</h2>
        <p>
          {gateway
            ? "Create a native LiteLLM key for one application and environment. This key both authorizes model calls and attributes their usage; no second monitoring key is needed."
            : accountSync
              ? "Create one sync credential for a device or user. It can report every provider enabled in CodexBar; you do not need a connection for each provider."
              : "Create a reporting credential for one application and environment. This is needed only for usage or job events sent outside the LLM gateway."}
        </p>
        <form
          className={gateway ? "catalog-form gateway-key-form" : "inline-form"}
          onSubmit={create}
        >
          <label>
            Connection name
            <input
              name="name"
              required
              maxLength={100}
              placeholder="AgentTrade production"
            />
          </label>
          <label>
            {accountSync
              ? "Device / user label"
              : gateway
                ? "Application (optional)"
                : "Application"}
            <input
              name="app"
              required={!gateway}
              maxLength={100}
              placeholder="agenttrade"
              defaultValue={
                source === "codex"
                  ? "codex_exec"
                  : source === "claude"
                    ? "claude-code"
                    : ""
              }
            />
          </label>
          <label>
            {gateway ? "Environment (optional)" : "Environment"}
            <input
              name="environment"
              required={!gateway}
              maxLength={50}
              placeholder="production"
            />
          </label>
          {gateway && (
            <>
              <p className="field-note">
                If omitted, application uses the connection name and environment
                uses the installation default. The resulting scope stays fixed
                when the label is renamed.
              </p>
              <GatewayModelPicker
                connection={gatewayConnection || null}
                value={selectedModels}
                onChange={setSelectedModels}
                refresh={refresh}
              />
            </>
          )}
          <button
            className="primary"
            disabled={busy || (gateway && !gatewayConnection)}
          >
            {gateway ? "Add connection LLM key" : "Add connection"}
          </button>
        </form>
        {secret && (
          <div className="secret">
            <strong>Save this key now. It will not be shown again.</strong>
            <code>{secret}</code>
            <button className="secondary" onClick={() => setSecret("")}>
              I have saved it
            </button>
          </div>
        )}
      </section>
      {editing && (
        <section className="panel form-panel">
          <h2>Edit connection</h2>
          <p>
            {editing.app} / {editing.environment}. Application scope and model
            permissions are fixed. Create a replacement connection to change
            them, then revoke the old one.
          </p>
          <form className="inline-form" onSubmit={save} key={editing.id}>
            <label>
              Connection name
              <input
                name="name"
                required
                maxLength={100}
                defaultValue={editing.name}
              />
            </label>
            {!gateway && (
              <label>
                Connection type
                <select
                  name="source_type"
                  defaultValue={editing.source_type || "sdk"}
                >
                  {credentialSources.map((item) => (
                    <option value={item.id} key={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            )}
            <button
              className="primary"
              disabled={busy || (gateway && !gatewayConnection)}
            >
              Save connection
            </button>
            <button
              className="secondary"
              type="button"
              disabled={busy}
              onClick={() => setEditing(null)}
            >
              Cancel
            </button>
          </form>
        </section>
      )}
      {gateway && routing && (
        <GatewayRouting
          key={`${tenant}:${routing.id}`}
          tenant={tenant}
          connection={routing}
          close={() => setRouting(null)}
          report={report}
        />
      )}
      <section className="panel">
        <div className="section-heading">
          <h2>Connections</h2>
          <KeyRound size={18} />
        </div>
        {keys.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Name</th>
                  <th>Scope</th>
                  <th>Expires</th>
                  <th>Status</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {keys.map((key) => (
                  <tr key={key.id} data-connection-id={key.id}>
                    <td>{key.name}</td>
                    <td>
                      {key.app}
                      <small>{key.environment}</small>
                      {!!key.allowed_models?.length && (
                        <small>{key.allowed_models.join(", ")}</small>
                      )}
                    </td>
                    <td>{new Date(key.expires_at).toLocaleDateString()}</td>
                    <td>
                      {key.revoked_at
                        ? "revoked"
                        : new Date(key.expires_at) < new Date()
                          ? "expired"
                          : "active"}
                    </td>
                    <td>
                      {gateway &&
                        !key.revoked_at &&
                        new Date(key.expires_at) > new Date() && (
                          <button
                            className="text-button connection-edit"
                            disabled={busy}
                            onClick={() => setRouting(key)}
                          >
                            Services &amp; default
                          </button>
                        )}
                      {!key.revoked_at && (
                        <button
                          className="text-button connection-edit"
                          disabled={busy}
                          onClick={() => setEditing(key)}
                        >
                          Edit
                        </button>
                      )}
                      {!key.revoked_at && (
                        <button
                          disabled={busy}
                          className="text-button"
                          onClick={() => revoke(key.id)}
                        >
                          Revoke
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p className="form-panel">
            No connections yet. Add one above to get started.
          </p>
        )}
      </section>
    </>
  );
}
