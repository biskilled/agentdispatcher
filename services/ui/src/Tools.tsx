import { useEffect, useState } from "react";
import { api } from "./api";

type Grant = { id: string; can_write_policy: boolean; expires_at: string };

/** Tool grants preserve the signed-in user's permissions and end when that session ends. */
export function ToolsView({
  tenant,
  role,
  report,
}: {
  tenant: string;
  role: string;
  report: (message: string) => void;
}) {
  const [grants, setGrants] = useState<Grant[]>([]);
  const [write, setWrite] = useState(false);
  const [secret, setSecret] = useState("");
  const [revision, setRevision] = useState(0);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    let active = true;
    api<Grant[]>("/tools/access", tenant)
      .then((value) => {
        if (active) setGrants(value);
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, report]);
  async function issue() {
    setBusy(true);
    try {
      const grant = await api<Grant & { secret: string }>(
        "/tools/access",
        tenant,
        { method: "POST", body: JSON.stringify({ can_write_policy: write }) },
      );
      setSecret(grant.secret);
      setRevision((value) => value + 1);
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  async function revoke(id: string) {
    try {
      await api(`/tools/access/${id}`, tenant, { method: "DELETE" });
      setRevision((value) => value + 1);
      setSecret("");
      report("Tool credential revoked.");
    } catch (error) {
      report((error as Error).message);
    }
  }
  return (
    <section className="panel form-panel">
      <h2>Delegate access to monitoring tools</h2>
      <p>
        Use this credential with the optional MCP service. Tools retain your
        current workspace and app permissions. Signing out, membership removal
        or revocation ends access immediately.
      </p>
      {["owner", "admin"].includes(role) && (
        <label className="checkbox-label">
          <input
            type="checkbox"
            checked={write}
            onChange={(event) => setWrite(event.target.checked)}
          />
          Also allow model policy changes
        </label>
      )}
      <button className="primary" disabled={busy} onClick={issue}>
        Create tool credential
      </button>
      {secret && (
        <div className="notice">
          <p>
            Save this credential in your MCP client's secret environment. It is
            shown once; never paste it into a prompt.
          </p>
          <code className="secret">{secret}</code>
          <button onClick={() => setSecret("")}>
            I have saved the tool credential
          </button>
        </div>
      )}
      {grants.map((grant) => (
        <div className="connection-row" key={grant.id} data-grant-id={grant.id}>
          <p>
            {grant.can_write_policy ? "Read and policy changes" : "Read only"} ·
            Expires {new Date(grant.expires_at).toLocaleString()} or when you
            sign out
          </p>
          <button onClick={() => revoke(grant.id)}>
            Revoke tool credential
          </button>
        </div>
      ))}
    </section>
  );
}
