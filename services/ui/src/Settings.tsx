import { useEffect, useState } from "react";
import { api } from "./api";
import { RetentionSettings } from "./Retention";
import { AccessView, JoinWorkspace, LinkGoogle } from "./Access";
import { AgentDeskView } from "./AgentDesk";
import { PoliciesView } from "./Policies";
import { ToolsView } from "./Tools";
import { OperationsView } from "./Operations";
import { ConfigurationsView } from "./Configurations";

const sections = [
  { group: "Workspace", id: "Workspace", label: "General", admin: true },
  { group: "Workspace", id: "Access", label: "Users & access", admin: true },
  { group: "Workspace", id: "Account", label: "Your account", admin: false },
  {
    group: "Workspace",
    id: "Invitations",
    label: "Workspace invitations",
    admin: false,
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

/** Show the complete permitted Settings menu beside the selected section. */
export function SettingsPage({
  tenant,
  userId,
  email,
  role,
  section,
  select,
  joined,
  report,
}: {
  tenant: string;
  userId: string;
  email: string;
  role: string;
  section: SettingsSection;
  select: (section: SettingsSection) => void;
  joined: (tenant: string) => void;
  report: (message: string) => void;
}) {
  const admin = ["owner", "admin"].includes(role);
  const available = sections.filter(
    (item) =>
      (admin || !item.admin) &&
      (tenant || ["Account", "Invitations"].includes(item.id)),
  );
  return (
    <div className="settings-layout">
      <nav className="settings-sidebar" aria-label="Settings navigation">
        {[...new Set(available.map((item) => item.group))].map((group) => (
          <div key={group}>
            <p className="settings-group">{group}</p>
            {available
              .filter((item) => item.group === group)
              .map((item) => (
                <button
                  key={item.id}
                  data-settings-section={item.id}
                  className={section === item.id ? "selected" : ""}
                  aria-current={section === item.id ? "page" : undefined}
                  onClick={() => select(item.id)}
                >
                  {item.label}
                </button>
              ))}
          </div>
        ))}
      </nav>
      <div className="settings-detail">
        {section === "Invitations" && (
          <JoinWorkspace key={userId} joined={joined} report={report} />
        )}
        {section === "Account" && (
          <section className="panel form-panel">
            <h2>Your account</h2>
            <p>
              Signed in as {email}.{role && ` Workspace role: ${role}.`}
            </p>
            <LinkGoogle report={report} />
          </section>
        )}
        {tenant && (
          <div key={`${tenant}-${section}`}>
            {section === "Workspace" && admin && (
              <SettingsView tenant={tenant} report={report} />
            )}
            {section === "Access" && admin && (
              <AccessView tenant={tenant} role={role} report={report} />
            )}
            {section === "AgentDesk" && (
              <AgentDeskView tenant={tenant} role={role} report={report} />
            )}
            {section === "Tool access" && (
              <ToolsView tenant={tenant} role={role} report={report} />
            )}
            {section === "Model policies" && admin && (
              <PoliciesView tenant={tenant} report={report} />
            )}
            {section === "Configuration" && admin && (
              <ConfigurationsView tenant={tenant} report={report} />
            )}
            {admin && (section === "Schedules" || section === "Budgets") && (
              <OperationsView
                tenant={tenant}
                section={section}
                report={report}
              />
            )}
          </div>
        )}
      </div>
    </div>
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
