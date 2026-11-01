import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

type Member = { id: string; email: string; role: string; apps: string[] };
type Invitation = {
  id: string;
  email: string;
  role: string;
  expires_at: string;
  accepted_at: string | null;
  revoked_at: string | null;
};
type Props = {
  tenant: string;
  role: string;
  report: (message: string) => void;
};

/** Tenant membership controls share the server's owner/admin permission boundary. */
export function AccessView({ tenant, role, report }: Props) {
  const [members, setMembers] = useState<Member[]>([]);
  const [invitations, setInvitations] = useState<Invitation[]>([]);
  const [secret, setSecret] = useState("");
  const [revision, setRevision] = useState(0);
  const roles =
    role === "owner"
      ? ["owner", "admin", "member", "viewer"]
      : ["member", "viewer"];
  useEffect(() => {
    let active = true;
    Promise.all([
      api<Member[]>("/members", tenant),
      api<Invitation[]>("/invitations", tenant),
    ])
      .then(([m, i]) => {
        if (active) {
          setMembers(m);
          setInvitations(i);
        }
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision, report]);
  async function invite(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      const result = await api<{ token: string }>("/invitations", tenant, {
        method: "POST",
        body: JSON.stringify(Object.fromEntries(new FormData(form))),
      });
      setSecret(result.token);
      setRevision((value) => value + 1);
      form.reset();
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function update(event: FormEvent<HTMLFormElement>, member: Member) {
    event.preventDefault();
    const data = new FormData(event.currentTarget);
    try {
      await api(`/members/${member.id}`, tenant, {
        method: "PUT",
        body: JSON.stringify({
          role: data.get("role") || null,
          apps: String(data.get("apps") || "")
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
        }),
      });
      setRevision((value) => value + 1);
      report("Membership updated. Permission changes take effect immediately.");
    } catch (error) {
      report((error as Error).message);
    }
  }
  async function revoke(id: string) {
    try {
      await api(`/invitations/${id}`, tenant, { method: "DELETE" });
      setRevision((value) => value + 1);
    } catch (error) {
      report((error as Error).message);
    }
  }
  return (
    <>
      <section className="panel form-panel">
        <h2>Invite to this workspace</h2>
        <p>The invited person must also sign in with their email account.</p>
        <form className="inline-form" onSubmit={invite}>
          <label>
            Email
            <input name="email" type="email" required />
          </label>
          <label>
            Role
            <select name="role" defaultValue="member">
              {roles.map((value) => (
                <option key={value}>{value}</option>
              ))}
            </select>
          </label>
          <button className="primary">Create invitation</button>
        </form>
        {secret && (
          <div className="notice">
            <p>
              Share this invitation token with the invited person. It is shown
              only once.
            </p>
            <code className="secret">{secret}</code>
            <button onClick={() => setSecret("")}>Dismiss token</button>
          </div>
        )}
      </section>
      <section className="panel form-panel">
        <h2>Members and app views</h2>
        <p>
          Members see their verified usage. Viewers need app grants. Enter
          comma-separated app names, or * for every app.
        </p>
        {members.map((member) => (
          <form
            className="inline-form"
            key={`${member.id}-${revision}`}
            onSubmit={(event) => update(event, member)}
          >
            <strong>{member.email}</strong>
            <label>
              Role for {member.email}
              <select
                name="role"
                defaultValue={member.role}
                disabled={
                  role !== "owner" && ["owner", "admin"].includes(member.role)
                }
              >
                {[...new Set([...roles, member.role])].map((value) => (
                  <option key={value}>{value}</option>
                ))}
                <option value="">Remove membership</option>
              </select>
            </label>
            <label>
              App views for {member.email}
              <input name="apps" defaultValue={member.apps.join(", ")} />
            </label>
            <button
              className="secondary"
              disabled={
                role !== "owner" && ["owner", "admin"].includes(member.role)
              }
            >
              Save access
            </button>
          </form>
        ))}
      </section>
      <section className="panel form-panel">
        <h2>Invitations</h2>
        {invitations.length === 0 && <p>No invitations yet.</p>}
        {invitations.map((invite) => (
          <div className="inline-form" key={invite.id}>
            <span>
              {invite.email} · {invite.role} ·{" "}
              {invite.accepted_at
                ? "Accepted"
                : invite.revoked_at
                  ? "Revoked"
                  : `Expires ${new Date(invite.expires_at).toLocaleString()}`}
            </span>
            {!invite.accepted_at && !invite.revoked_at && (
              <button className="secondary" onClick={() => revoke(invite.id)}>
                Revoke invitation
              </button>
            )}
          </div>
        ))}
      </section>
    </>
  );
}

/** Accept invitations only after independent sign-in, including accounts without memberships. */
export function JoinWorkspace({
  joined,
  report,
}: {
  joined: () => void;
  report: (message: string) => void;
}) {
  async function accept(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    try {
      await api("/invitations/accept", undefined, {
        method: "POST",
        body: JSON.stringify({ token: new FormData(form).get("token") }),
      });
      form.reset();
      joined();
    } catch (error) {
      report((error as Error).message);
    }
  }
  return (
    <details className="panel form-panel">
      <summary>Join another workspace</summary>
      <form className="inline-form" onSubmit={accept}>
        <label>
          Invitation token
          <input
            name="token"
            autoComplete="off"
            required
            minLength={32}
            maxLength={256}
          />
        </label>
        <button className="primary">Accept invitation</button>
      </form>
    </details>
  );
}

/** Explicit linking requires fresh server-verified login and never matches accounts by email. */
export function LinkGoogle({ report }: { report: (message: string) => void }) {
  const [enabled, setEnabled] = useState(false);
  useEffect(() => {
    api<{ google: boolean }>("/auth/providers")
      .then((result) => setEnabled(result.google))
      .catch((error) => report(error.message));
  }, [report]);
  async function link() {
    try {
      const result = await api<{ url: string }>(
        "/auth/google/link",
        undefined,
        { method: "POST" },
      );
      location.assign(result.url);
    } catch (error) {
      report((error as Error).message);
    }
  }
  return enabled ? (
    <button className="secondary" onClick={link}>
      Link a Google account
    </button>
  ) : null;
}
