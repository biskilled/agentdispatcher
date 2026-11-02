import { useEffect, useState } from "react";
import { api } from "./api";

type Destination = "Access" | "SDK keys" | "LLM keys" | "Connections" | "API catalog" | "Overview";
type Status = {
  database_ready: boolean;
  worker: { healthy: boolean; last_seen: string | null };
  configured: Record<string, boolean>;
  sources: { app: string; environment: string; source: string; attempts: number; first_seen: string; last_seen: string; stale: boolean }[];
  source_limit: number;
};
const steps: { title: string; description: string; destination: Destination }[] = [
  { title: "1. Choose who can access this workspace", description: "Invite members and assign their application views. Signing in does not automatically grant workspace membership.", destination: "Access" },
  { title: "2. Connect an application or CLI", description: "Create a separate SDK key for each application and environment. Store it on the application server or local CLI, then follow the source guide in Connections.", destination: "SDK keys" },
  { title: "3. Configure model routing when needed", description: "For routed LLM calls, enable LiteLLM on the server and create an LLM key. Provider secrets stay in deployment configuration. Telemetry-only clients can skip this step.", destination: "LLM keys" },
  { title: "4. Describe API pricing", description: "Register paid or free API plans and quota rules. An API without a known plan remains unpriced; it is not treated as free.", destination: "API catalog" },
  { title: "5. Send a first request", description: "Run an instrumented application job or CLI request. Refresh this page to verify receipt, then inspect delivery gaps in Connections.", destination: "Connections" },
];

/** Guide setup using observed evidence and existing administration flows. */
export function SetupView({ tenant, navigate, report }: {
  tenant: string; navigate: (destination: Destination) => void; report: (message: string) => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setStatus(null);
    api<Status>("/setup/status", tenant).then((value) => { if (active) setStatus(value); })
      .catch((error) => { if (active) report(error.message); });
    return () => { active = false; };
  }, [tenant, revision, report]);
  return <>
    <section className="panel form-panel">
      <h2>Set up your workspace</h2>
      <p>Connect one source, verify its first event, then add the rest of your applications.</p>
      <button className="secondary" onClick={() => setRevision((value) => value + 1)}>Check setup status</button>
      {!status && <p role="status">Checking installation…</p>}
      {status && <>
        <p>Database: {status.database_ready ? "Ready" : "Unavailable"}. Worker: {status.worker.healthy ? "Reporting" : "No recent heartbeat"}.</p>
        <p>Login configuration: Google {status.configured.google ? "configured" : "not configured"}; email {status.configured.email ? "configured" : "not configured"}.</p>
        <p>Gateway: {status.configured.gateway ? "configured" : "not configured"}. AgentDesk: {status.configured.agentdesk ? "configured" : "not configured"}.</p>
        <p className="muted">Configuration is not proof of a successful login or provider connection. Test enabled login methods separately.</p>
        {!status.configured.https && <p>Local HTTP mode. To access this installation from mobile, configure an authenticated HTTPS deployment and secure cookies using the deployment guide.</p>}
      </>}
    </section>
    {steps.map((step) => <section className="panel form-panel" key={step.destination}>
      <h2>{step.title}</h2><p>{step.description}</p>
      <button className="secondary" onClick={() => navigate(step.destination)}>Open {step.destination}</button>
    </section>)}
    <section className="panel form-panel">
      <h2>First-event evidence</h2>
      {status?.sources.length === 0 && <p>No usage received yet. A configured key alone does not prove the application is reporting.</p>}
      {status && status.sources.length > 0 && <>
        <p>Showing up to {status.source_limit} recently reporting source groups. Stale means no recent delivery; it does not prove the application stopped running.</p>
        <div className="table-scroll"><table><thead><tr><th>Application</th><th>Environment / source</th><th>Attempts</th><th>First received</th><th>Delivery</th></tr></thead>
          <tbody>{status.sources.map((row) => <tr key={`${row.app}/${row.environment}/${row.source}`}>
            <td>{row.app}</td><td>{row.environment} / {row.source}</td><td>{row.attempts}</td>
            <td>{new Date(row.first_seen).toLocaleString()}</td><td>{row.stale ? "Stale" : "Received"}</td>
          </tr>)}</tbody></table></div>
      </>}
      <button className="primary" onClick={() => navigate("Overview")}>View usage</button>
    </section>
  </>;
}
