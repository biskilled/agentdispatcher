import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

type Connection = {
  configured: boolean;
  bound: boolean;
  client_id: string | null;
  linked: boolean;
};

/** Explicit tenant binding and personal linking never grant a new workspace membership. */
export function AgentDeskView({
  tenant,
  role,
  report,
}: {
  tenant: string;
  role: string;
  report: (message: string) => void;
}) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api<Connection>("/agentdesk/connection", tenant)
      .then((result) => {
        if (active) setConnection(result);
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, report]);

  async function connect(event: FormEvent<HTMLFormElement>, action: string) {
    event.preventDefault();
    const form = event.currentTarget;
    const token = String(new FormData(form).get("token") || "");
    form.reset();
    setBusy(true);
    try {
      await api(`/agentdesk/${action}`, tenant, {
        method: "POST",
        body: JSON.stringify({ token }),
      });
      setRevision((value) => value + 1);
      report(
        action === "bind"
          ? "AgentDesk tenant connected. Link your own account next."
          : "Your AgentDesk account is linked.",
      );
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function disconnect(action: string) {
    setBusy(true);
    try {
      await api(`/agentdesk/${action}`, tenant, { method: "DELETE" });
      setRevision((value) => value + 1);
      report("AgentDesk access removed.");
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <section className="panel form-panel">
      <h2>Connect AgentDesk</h2>
      <p>
        Keep your existing workspace permissions when reading usage from
        AgentDesk. Sign in again before connecting if your last sign-in is no
        longer recent.
      </p>
      {connection && !connection.configured && (
        <p className="notice">
          An operator must configure the AgentDesk identity connection for this
          installation.
        </p>
      )}
      {connection?.bound && (
        <p>
          Connected AgentDesk tenant: <strong>{connection.client_id}</strong>.
          Your account is {connection.linked ? "linked" : "not linked"}.
        </p>
      )}
      {connection?.configured &&
        ((!connection.bound && role === "owner") ||
          (connection.bound && !connection.linked)) && (
          <form
            className="inline-form"
            onSubmit={(event) =>
              connect(event, connection.bound ? "link" : "bind")
            }
          >
            <label>
              {connection.bound
                ? "Your AgentDesk access token"
                : "AgentDesk tenant administrator token"}
              <input
                name="token"
                type="password"
                autoComplete="off"
                required
                maxLength={16384}
              />
            </label>
            <button className="primary" disabled={busy}>
              {connection.bound ? "Link my account" : "Connect tenant"}
            </button>
            <p>
              The token is used for verification and is not saved. Integration
              keys cannot link a human account.
            </p>
          </form>
        )}
      {connection?.linked && (
        <button disabled={busy} onClick={() => disconnect("link")}>
          Unlink my account
        </button>
      )}
      {connection?.bound && role === "owner" && (
        <button disabled={busy} onClick={() => disconnect("bind")}>
          Disconnect tenant and all account links
        </button>
      )}
    </section>
  );
}
