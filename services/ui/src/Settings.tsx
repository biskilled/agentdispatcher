import { useEffect, useState } from "react";
import { api } from "./api";
import { RetentionSettings } from "./Retention";

const sections = [
  { group: "Workspace", id: "Workspace", label: "General", admin: true },
  { group: "Workspace", id: "Access", label: "Users & access", admin: true },
  { group: "Workspace", id: "Account", label: "Your account", admin: false },
  {
    group: "Application connections",
    id: "SDK keys",
    label: "SDK keys",
    admin: true,
  },
  {
    group: "Application connections",
    id: "API catalog",
    label: "API catalog & pricing",
    admin: true,
  },
  {
    group: "Monitoring",
    id: "Schedules",
    label: "Expected schedules",
    admin: true,
  },
  {
    group: "Monitoring",
    id: "Budgets",
    label: "Budgets & statements",
    admin: true,
  },
  {
    group: "Optional integrations & controls",
    id: "AgentDesk",
    label: "AgentDesk",
    admin: false,
  },
  {
    group: "Optional integrations & controls",
    id: "LLM keys",
    label: "LLM gateway keys",
    admin: true,
  },
  {
    group: "Optional integrations & controls",
    id: "Model policies",
    label: "Model routing",
    admin: true,
  },
  {
    group: "Optional integrations & controls",
    id: "Configuration",
    label: "Application configuration",
    admin: true,
  },
  {
    group: "Optional integrations & controls",
    id: "Tool access",
    label: "MCP tool access",
    admin: false,
  },
] as const;

export type SettingsSection = (typeof sections)[number]["id"];

/** Keep administration off the daily monitoring navigation, with role-appropriate choices. */
export function SettingsNavigation({
  section,
  select,
  admin,
}: {
  section: SettingsSection;
  select: (section: SettingsSection) => void;
  admin: boolean;
}) {
  const available = sections.filter((item) => admin || !item.admin);
  return (
    <section className="panel form-panel">
      <label>
        Settings section
        <select
          aria-label="Settings section"
          value={section}
          onChange={(event) => select(event.target.value as SettingsSection)}
        >
          {[...new Set(available.map((item) => item.group))].map((group) => (
            <optgroup key={group} label={group}>
              {available
                .filter((item) => item.group === group)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
            </optgroup>
          ))}
        </select>
      </label>
    </section>
  );
}

type Status = {
  database_ready: boolean;
  worker: { healthy: boolean; last_seen: string | null };
  configured: Record<string, boolean>;
  sources: {
    app: string;
    environment: string;
    source: string;
    attempts: number;
    first_seen: string;
    last_seen: string;
    stale: boolean;
  }[];
  source_limit: number;
};
/** Keep installation diagnostics and workspace-wide controls in one place. */
export function SettingsView({
  tenant,
  report,
}: {
  tenant: string;
  report: (message: string) => void;
}) {
  const [status, setStatus] = useState<Status | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    let active = true;
    setStatus(null);
    api<Status>("/setup/status", tenant)
      .then((value) => {
        if (active) setStatus(value);
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, report]);
  return (
    <>
      <section className="panel form-panel">
        <h2>Installation status</h2>
        <p>
          Login providers and integration credentials are configured through
          deployment environment variables. Workspace retention can be changed
          below.
        </p>
        <button
          className="secondary"
          onClick={() => setRevision((value) => value + 1)}
        >
          Refresh installation status
        </button>
        {!status && <p role="status">Checking installation…</p>}
        {status && (
          <>
            <p>
              Database: {status.database_ready ? "Ready" : "Unavailable"}.
              Worker:{" "}
              {status.worker.healthy ? "Reporting" : "No recent heartbeat"}.
            </p>
            <p>
              Login configuration: Google{" "}
              {status.configured.google ? "configured" : "not configured"};
              email {status.configured.email ? "configured" : "not configured"};
              temporary password{" "}
              {status.configured.password ? "enabled" : "disabled"}.
            </p>
            <p>
              Gateway:{" "}
              {status.configured.gateway ? "configured" : "not configured"}.
              AgentDesk:{" "}
              {status.configured.agentdesk ? "configured" : "not configured"}.
            </p>
            <p className="muted">
              Configuration is not proof of a successful login or provider
              connection. Test enabled login methods separately.
            </p>
            {!status.configured.https && (
              <p>
                Local HTTP mode. To access this installation from mobile,
                configure an authenticated HTTPS deployment and secure cookies
                using the deployment guide.
              </p>
            )}
          </>
        )}
      </section>
      <RetentionSettings tenant={tenant} report={report} />
    </>
  );
}
