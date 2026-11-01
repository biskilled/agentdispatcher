import React, { useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import {
  Activity,
  ArrowUpRight,
  Box,
  Check,
  ChevronRight,
  Database,
  KeyRound,
  Layers,
  LogOut,
  RefreshCw,
  Shield,
  Workflow,
} from "lucide-react";
import {
  api,
  money,
  type Job,
  type Key,
  type Overview,
  type Plan,
  type Usage,
  type User,
} from "./api";
import "./style.css";
import { Credits } from "./Credits";
import { CatalogView } from "./Accounting";
import { AccessView, JoinWorkspace, LinkGoogle } from "./Access";
import { UsageControls, UsageCharts, AttemptDetail } from "./UsageControls";
import { OperationsView } from "./Operations";
import { repository as sourceUrl } from "../../../package.json";

type Tab =
  | "Overview"
  | "Job runs"
  | "API catalog"
  | "SDK keys"
  | "Access"
  | "Schedules"
  | "Budgets";
const navigation = [
  { label: "Overview", icon: Activity },
  { label: "Job runs", icon: Workflow },
  { label: "API catalog", icon: Database },
  { label: "SDK keys", icon: KeyRound },
  { label: "Access", icon: Shield },
  { label: "Schedules", icon: Workflow },
  { label: "Budgets", icon: Database },
] as const;

function Login({ onLogin }: { onLogin: () => void }) {
  const [email, setEmail] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);
  const [providers, setProviders] = useState({ google: false, email: false });
  const [token] = useState(() =>
    new URLSearchParams(location.hash.slice(1)).get("signin"),
  );
  useEffect(() => {
    api<typeof providers>("/auth/providers")
      .then(setProviders)
      .catch((e) => setMessage(e.message));
    if (token) history.replaceState(null, "", location.pathname);
  }, [token]);
  async function submit(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      if (token) {
        await api("/auth/email/consume", undefined, {
          method: "POST",
          body: JSON.stringify({ token }),
        });
        onLogin();
      } else {
        const result = await api<{ message: string }>(
          "/auth/email/request",
          undefined,
          { method: "POST", body: JSON.stringify({ email }) },
        );
        setMessage(result.message);
      }
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="login">
      <div className="login-story">
        <Brand />
        <h1>
          Every call.
          <br />A clearer picture.
        </h1>
        <p>
          Understand the API requests, model calls and background jobs behind
          your applications.
        </p>
        <div className="login-line">
          <Workflow size={22} />
          <span>Applications</span>
          <ChevronRight />
          <span>Usage</span>
          <ChevronRight />
          <span>Insight</span>
        </div>
      </div>
      <main className="login-panel">
        <Shield className="login-icon" />
        <h2>Welcome to AgentDispatcher</h2>
        <p>Sign in to your workspace.</p>
        <form onSubmit={submit}>
          {!token && (
            <label>
              Email address
              <input
                type="email"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                autoComplete="email"
                required
                placeholder="you@company.com"
              />
            </label>
          )}
          <button
            className="primary"
            disabled={busy || (!token && !providers.email)}
          >
            {busy
              ? "Please wait…"
              : token
                ? "Continue to workspace"
                : "Email me a sign-in link"}
          </button>
        </form>
        {providers.google && (
          <a className="secondary google" href="/api/auth/google/start">
            Continue with Google
          </a>
        )}
        {!providers.email && !token && (
          <p className="muted">
            Email sign-in is not configured. Ask your installation administrator
            to enable it.
          </p>
        )}
        {message && (
          <p role="status" className="notice">
            {message}
          </p>
        )}
        <p className="login-foot">
          Your workspace membership determines what you can access.
        </p>
      </main>
    </div>
  );
}

function Brand() {
  return (
    <div className="brand">
      <div className="brand-mark">
        <Layers size={22} />
      </div>
      <span>
        Agent<span className="brand-light">Dispatcher</span>
      </span>
    </div>
  );
}
function Status({ value }: { value: string }) {
  return (
    <span className={`status ${value}`}>
      {value === "success" || value === "completed" ? (
        <Check size={12} />
      ) : (
        <span className="status-dot" />
      )}
      {value.replaceAll("_", " ")}
    </span>
  );
}
function Empty({ children }: { children: React.ReactNode }) {
  return (
    <div className="empty">
      <Box size={28} />
      <p>{children}</p>
    </div>
  );
}

function OverviewView({
  overview,
  events,
  tenant,
}: {
  overview: Overview | null;
  events: Usage[];
  tenant: string;
}) {
  if (!overview) return <p className="muted">Loading usage…</p>;
  const { counts, totals, breakdown } = overview;
  return (
    <>
      <div className="metrics">
        <div>
          <span>Observed attempts</span>
          <strong>{counts.attempts.toLocaleString()}</strong>
          <small>Across connected applications</small>
        </div>
        <div>
          <span>Known usage cost</span>
          <strong className="cost-value">
            {totals
              .filter((t) => t.cost !== null)
              .map((t, i) => (
                <span key={i}>
                  {money(t.cost, t.currency)}
                  <small>{t.cost_kind.replaceAll("_", " ")}</small>
                </span>
              ))}
            {totals.every((t) => t.cost === null) && "—"}
          </strong>
          <small>Calculated costs; not an invoice</small>
        </div>
        <div>
          <span>Unpriced attempts</span>
          <strong>{counts.unknown_cost.toLocaleString()}</strong>
          <small>
            {counts.unknown_cost
              ? "Add pricing to improve coverage"
              : "No unpriced observations"}
          </small>
        </div>
        <div>
          <span>Failed attempts</span>
          <strong>{counts.failures.toLocaleString()}</strong>
          <small>Errors and timeouts</small>
        </div>
      </div>
      <div className="overview-grid">
        <section className="panel">
          <div className="section-heading">
            <div>
              <h2>Usage by application</h2>
              <p>Each provider and cost category stays visible.</p>
            </div>
            <Layers size={18} />
          </div>
          {breakdown.length ? (
            <div className="breakdowns">
              {breakdown.map((row, i) => (
                <div className="breakdown" key={i}>
                  <div className="app-icon">
                    <Box size={18} />
                  </div>
                  <div className="breakdown-name">
                    <strong>{row.app}</strong>
                    <span>
                      {row.provider} / {row.resource_kind}
                    </span>
                  </div>
                  <div className="bar">
                    <span
                      style={{
                        width: `${Math.max(2, (row.attempts / Math.max(counts.attempts, 1)) * 100)}%`,
                      }}
                    />
                  </div>
                  <div className="breakdown-value">
                    <strong>{money(row.cost, row.currency)}</strong>
                    <span>{row.attempts} attempts</span>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <Empty>
              Connect an application with an SDK key to see its usage here.
            </Empty>
          )}
        </section>
        <aside className="coverage">
          <div className="coverage-icon">
            <Shield size={23} />
          </div>
          <h2>Know what is measured</h2>
          <p>
            This view includes calls reported by your connected applications.
            Uninstrumented calls are outside its coverage.
          </p>
          <div className="coverage-detail">
            <span>Cost evidence</span>
            <strong>Configured pricing</strong>
          </div>
          <div className="coverage-detail">
            <span>User attribution</span>
            <strong>Verified, app-reported or service</strong>
          </div>
          <div className="coverage-detail">
            <span>Last event received</span>
            <strong>
              {counts.last_received_at
                ? new Date(counts.last_received_at).toLocaleString()
                : "No events yet"}
            </strong>
          </div>
        </aside>
      </div>
      <UsageCharts overview={overview} />
      <section className="panel">
        <div className="section-heading">
          <div>
            <h2>Recent activity</h2>
            <p>Latest physical attempts, with duplicate exports removed.</p>
          </div>
          <span className="count">{events.length} shown</span>
        </div>
        {events.length ? (
          <div className="table-scroll">
            <table>
              <thead>
                <tr>
                  <th>Application</th>
                  <th>Provider / model</th>
                  <th>Result</th>
                  <th>Cost</th>
                  <th>Time</th>
                  <th>Evidence</th>
                </tr>
              </thead>
              <tbody>
                {events.map((event) => (
                  <tr key={event.event_id}>
                    <td>
                      <strong>{event.app}</strong>
                      <small>{event.resource_kind}</small>
                    </td>
                    <td>
                      {event.provider}
                      <small>{event.model || "API operation"}</small>
                    </td>
                    <td>
                      <Status value={event.status} />
                    </td>
                    <td>
                      {money(event.cost, event.currency)}
                      <small>{event.cost_kind.replaceAll("_", " ")}</small>
                    </td>
                    <td>{new Date(event.occurred_at).toLocaleTimeString()}</td>
                    <td>
                      <AttemptDetail tenant={tenant} eventId={event.event_id} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty>Your first instrumented request will appear here.</Empty>
        )}
      </section>
    </>
  );
}

function JobsView({ jobs }: { jobs: Job[] }) {
  return (
    <section className="panel">
      <div className="section-heading">
        <div>
          <h2>Scheduled and background work</h2>
          <p>
            Runs are reported by your applications; stale means no recent
            heartbeat.
          </p>
        </div>
      </div>
      {jobs.length ? (
        <div className="table-scroll">
          <table>
            <thead>
              <tr>
                <th>Job</th>
                <th>Application</th>
                <th>State</th>
                <th>Last event</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map((job) => (
                <tr key={job.run_id}>
                  <td>
                    <strong>{job.name}</strong>
                    <small>{job.run_id.slice(0, 8)}</small>
                  </td>
                  <td>{job.app}</td>
                  <td>
                    <Status value={job.stale ? "stale" : job.state} />
                  </td>
                  <td>{new Date(job.occurred_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <Empty>
          Wrap a scheduler entrypoint with the SDK to see run health.
        </Empty>
      )}
    </section>
  );
}

function KeyView({
  tenant,
  keys,
  refresh,
  report,
}: {
  tenant: string;
  keys: Key[];
  refresh: () => void;
  report: (s: string) => void;
}) {
  const [secret, setSecret] = useState("");
  async function create(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    const data = Object.fromEntries(new FormData(form));
    try {
      const result = await api<{ secret: string }>("/keys", tenant, {
        method: "POST",
        body: JSON.stringify(data),
      });
      setSecret(result.secret);
      form.reset();
      refresh();
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function revoke(id: string) {
    try {
      await api(`/keys/${id}`, tenant, { method: "DELETE" });
      refresh();
    } catch (error) {
      report((error as Error).message);
    }
  }
  return (
    <>
      <section className="panel form-panel">
        <h2>Connect an application</h2>
        <p>
          Create a key for one application and environment. Store it in your
          backend’s secret store.
        </p>
        <form className="inline-form" onSubmit={create}>
          <label>
            Key name
            <input
              name="name"
              required
              maxLength={100}
              placeholder="Advisor production"
            />
          </label>
          <label>
            Application
            <input
              name="app"
              required
              maxLength={100}
              placeholder="agenttrade"
            />
          </label>
          <label>
            Environment
            <input
              name="environment"
              required
              maxLength={50}
              placeholder="production"
            />
          </label>
          <button className="primary">Create key</button>
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
      <section className="panel">
        <div className="section-heading">
          <h2>Application keys</h2>
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
                  <tr key={key.id}>
                    <td>{key.name}</td>
                    <td>
                      {key.app}
                      <small>{key.environment}</small>
                    </td>
                    <td>{new Date(key.expires_at).toLocaleDateString()}</td>
                    <td>
                      <Status value={key.revoked_at ? "revoked" : "active"} />
                    </td>
                    <td>
                      {!key.revoked_at && (
                        <button
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
          <Empty>No application keys yet.</Empty>
        )}
      </section>
    </>
  );
}

function App() {
  const [user, setUser] = useState<User | null>(null);
  const [checking, setChecking] = useState(true);
  const [tenant, setTenant] = useState("");
  const [tab, setTab] = useState<Tab>("Overview");
  const [overview, setOverview] = useState<Overview | null>(null);
  const [events, setEvents] = useState<Usage[]>([]);
  const [jobs, setJobs] = useState<Job[]>([]);
  const [keys, setKeys] = useState<Key[]>([]);
  const [plans, setPlans] = useState<Plan[]>([]);
  const [message, setMessage] = useState("");
  const [revision, setRevision] = useState(0);
  const [loading, setLoading] = useState(false);
  const [filters, setFilters] = useState("");
  const [offset, setOffset] = useState(0);
  const current = user?.tenants.find((t) => t.tenant_id === tenant);
  const admin = ["owner", "admin"].includes(current?.role || "");
  async function loadUser() {
    try {
      const next = await api<User>("/auth/me");
      setUser(next);
      setTenant(next.tenants[0]?.tenant_id || "");
    } catch {
      setUser(null);
    } finally {
      setChecking(false);
    }
  }
  useEffect(() => {
    void loadUser();
  }, []);
  useEffect(() => {
    setOverview(null);
    setEvents([]);
    setJobs([]);
    setKeys([]);
    setPlans([]);
    if (!tenant) return;
    let cancelled = false;
    setLoading(true);
    Promise.all([
      api<Overview>(`/overview?${filters}`, tenant),
      api<Usage[]>(`/events?${filters}&offset=${offset}`, tenant),
      api<Job[]>("/jobs", tenant),
      admin ? api<Key[]>("/keys", tenant) : Promise.resolve([]),
      admin ? api<Plan[]>("/plans", tenant) : Promise.resolve([]),
    ])
      .then(([o, e, j, k, p]) => {
        if (!cancelled) {
          setOverview(o);
          setEvents(e);
          setJobs(j);
          setKeys(k);
          setPlans(p);
        }
      })
      .catch((error) => {
        if (!cancelled) setMessage(error.message);
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [tenant, revision, admin, filters, offset]);
  useEffect(() => {
    setMessage("");
    setOffset(0);
    setFilters("");
  }, [tenant]);
  useEffect(() => {
    if (!admin) setTab("Overview");
  }, [admin]);
  if (checking)
    return <div className="loading">Connecting to your workspace…</div>;
  if (!user) return <Login onLogin={loadUser} />;
  const refresh = () => setRevision((r) => r + 1);
  async function logout() {
    try {
      await api("/auth/logout", undefined, { method: "POST" });
      setUser(null);
      setTenant("");
    } catch (error) {
      setMessage((error as Error).message);
    }
  }
  return (
    <div className="shell">
      <aside className="sidebar">
        <Brand />
        <div className="workspace-label">Workspace</div>
        <select
          aria-label="Workspace"
          value={tenant}
          onChange={(e) => setTenant(e.target.value)}
        >
          {user.tenants.map((t) => (
            <option key={t.tenant_id} value={t.tenant_id}>
              {t.name}
            </option>
          ))}
        </select>
        <nav aria-label="Main navigation">
          {navigation
            .filter(
              ({ label }) => admin || ["Overview", "Job runs"].includes(label),
            )
            .map(({ label, icon: Icon }) => (
              <button
                key={label}
                className={tab === label ? "selected" : ""}
                onClick={() => setTab(label)}
              >
                <Icon size={19} />
                {label}
                {tab === label && <span className="nav-indicator" />}
              </button>
            ))}
        </nav>
        <div className="sidebar-note">
          <div>
            <Shield size={17} />
            Tenant-isolated
          </div>
          <p>
            Your applications.
            <br />
            Your usage data.
          </p>
        </div>
        <div className="user">
          <div className="avatar">{user.email[0].toUpperCase()}</div>
          <div>
            <strong>{user.email}</strong>
            <span>{current?.role || "No membership"}</span>
          </div>
          <button aria-label="Sign out" onClick={logout}>
            <LogOut size={17} />
          </button>
        </div>
      </aside>
      <main className="content">
        <header className="topbar">
          <span>
            {current?.name || "Workspace"}
            <ChevronRight size={14} />
            {tab}
          </span>
          <span className="build-tag">Initial release</span>
          <button
            className="mobile-logout"
            aria-label="Sign out"
            onClick={logout}
          >
            <LogOut size={16} />
          </button>
        </header>
        <div className="page">
          <header className="page-heading">
            <div>
              <h1>{tab === "Overview" ? "Usage overview" : tab}</h1>
              <p>
                {tab === "Overview"
                  ? "Follow the calls and background work across your applications."
                  : tab === "Job runs"
                    ? "See what ran, what failed, and what stopped reporting."
                    : tab === "API catalog"
                      ? "Define the services and pricing your applications use."
                      : "Manage scoped credentials for your applications."}
              </p>
            </div>
            <button className="secondary" onClick={refresh} disabled={loading}>
              <RefreshCw size={16} />
              {loading ? "Refreshing…" : "Refresh"}
            </button>
          </header>
          {message && (
            <div className="notice" role="status">
              {message}
            </div>
          )}
          <JoinWorkspace joined={loadUser} report={setMessage} />
          <LinkGoogle report={setMessage} />
          {!tenant ? (
            <Empty>
              Your account is signed in but has no workspace membership. Ask an
              administrator to provision access.
            </Empty>
          ) : (
            <div key={tenant}>
              {tab === "Overview" && (
                <>
                  <UsageControls
                    apply={(query) => {
                      setFilters(query);
                      setOffset(0);
                    }}
                  />
                  <OverviewView
                    overview={overview}
                    events={events}
                    tenant={tenant}
                  />
                  <div className="inline-form">
                    <button
                      className="secondary"
                      disabled={offset === 0 || loading}
                      onClick={() =>
                        setOffset(
                          Math.max(
                            0,
                            offset - (overview?.chart_row_limit || 100),
                          ),
                        )
                      }
                    >
                      Previous attempts
                    </button>
                    <span>
                      Showing {offset + (events.length ? 1 : 0)}–
                      {offset + events.length}
                    </span>
                    <button
                      className="secondary"
                      disabled={
                        loading ||
                        !overview ||
                        offset + events.length >= overview.counts.attempts
                      }
                      onClick={() => setOffset(offset + events.length)}
                    >
                      Next attempts
                    </button>
                  </div>
                </>
              )}{" "}
              {tab === "Job runs" && <JobsView jobs={jobs} />}{" "}
              {admin && (tab === "Schedules" || tab === "Budgets") && (
                <OperationsView
                  tenant={tenant}
                  section={tab}
                  report={setMessage}
                />
              )}
              {tab === "Access" && admin && (
                <AccessView
                  tenant={tenant}
                  role={current?.role || ""}
                  report={setMessage}
                />
              )}
              {tab === "API catalog" && admin && (
                <CatalogView
                  tenant={tenant}
                  plans={plans}
                  refresh={refresh}
                  report={setMessage}
                />
              )}{" "}
              {tab === "SDK keys" && admin && (
                <KeyView
                  tenant={tenant}
                  keys={keys}
                  refresh={refresh}
                  report={setMessage}
                />
              )}
            </div>
          )}
          <footer>
            <span>AgentDispatcher · Apache 2.0</span>
            <Credits />
            <a href={sourceUrl} target="_blank" rel="noreferrer">
              Source & credits <ArrowUpRight size={13} />
            </a>
          </footer>
        </div>
      </main>
    </div>
  );
}

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <App />
  </React.StrictMode>,
);
