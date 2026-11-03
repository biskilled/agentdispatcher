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
  const [invitation, setInvitation] = useState<{
    invitation_url: string;
    delivery: string;
  } | null>(null);
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
      const result = await api<{ invitation_url: string; delivery: string }>(
        "/invitations",
        tenant,
        {
          method: "POST",
          body: JSON.stringify(Object.fromEntries(new FormData(form))),
        },
      );
      setInvitation(result);
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
        <p>
          The recipient signs in with the invited email, then selects Accept
          invitation to join this workspace.
        </p>
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
        {invitation && (
          <div className="notice">
            <p>
              {invitation.delivery === "sent"
                ? "Invitation emailed. You can also share the link below."
                : invitation.delivery === "failed"
                  ? "Invitation created, but email delivery failed. Share the link below."
                  : "Invitation created. Email delivery is not configured. Share the link below."}
            </p>
            <label>
              Invitation link
              <input
                readOnly
                value={invitation.invitation_url}
                onFocus={(event) => event.target.select()}
              />
            </label>
            <button
              onClick={async () => {
                try {
                  await navigator.clipboard.writeText(
                    invitation.invitation_url,
                  );
                  report("Invitation link copied.");
                } catch {
                  report(
                    "Copy unavailable. Select and copy the invitation link above.",
                  );
                }
              }}
            >
              Copy invitation link
            </button>
            <button onClick={() => setInvitation(null)}>Dismiss link</button>
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

type PendingInvitation = {
  id: string;
  workspace_name: string;
  role: string;
  expires_at: string;
};

/** The signed-in recipient accepts directly; mailbox ownership replaces manual token entry. */
export function JoinWorkspace({
  joined,
  report,
}: {
  joined: (tenant: string) => void;
  report: (message: string) => void;
}) {
  const [invitations, setInvitations] = useState<PendingInvitation[]>([]);
  const [busy, setBusy] = useState(false);
  const [accepted, setAccepted] = useState("");
  const [revision, setRevision] = useState(0);
  const [requested, setRequested] = useState(() =>
    new URLSearchParams(location.hash.slice(1)).get("invite"),
  );
  useEffect(() => {
    let active = true;
    api<PendingInvitation[]>("/invitations/pending")
      .then((value) => {
        if (active) setInvitations(value);
      })
      .catch((error) => {
        if (active) report(error.message);
      });
    return () => {
      active = false;
    };
  }, [revision, report]);
  async function accept(invitation: PendingInvitation) {
    if (busy) return;
    setBusy(true);
    try {
      const result = await api<{ tenant_id: string }>(
        `/invitations/${invitation.id}/accept`,
        undefined,
        { method: "POST" },
      );
      setInvitations((items) =>
        items.filter((item) => item.id !== invitation.id),
      );
      if (requested === invitation.id) {
        history.replaceState(null, "", location.pathname);
        setRequested(null);
      }
      joined(result.tenant_id);
      setAccepted(invitation.workspace_name);
    } catch (error) {
      report((error as Error).message);
    } finally {
      setBusy(false);
    }
  }
  return (
    <>
      {accepted && (
        <p className="notice" role="status">
          Joined {accepted}.
        </p>
      )}
      <section className="panel form-panel">
        <h2>
          Workspace invitations
          {invitations.length ? ` (${invitations.length})` : ""}
        </h2>
        <p>
          Invitations are matched to your signed-in email. Accept to join and
          open that workspace.
        </p>
        {invitations.length === 0 && (
          <p>
            No pending invitations for this account. If you received a link,
            check that you signed in with the invited email; the invitation may
            also have expired or been revoked.
          </p>
        )}
        {invitations.map((invitation) => (
          <div className="inline-form" key={invitation.id}>
            <span>
              {invitation.workspace_name} · {invitation.role} · Expires{" "}
              {new Date(invitation.expires_at).toLocaleString()}
            </span>
            <button
              className="primary"
              disabled={busy}
              onClick={() => accept(invitation)}
            >
              Accept invitation to {invitation.workspace_name}
            </button>
          </div>
        ))}
        <button
          className="secondary"
          disabled={busy}
          onClick={() => setRevision((value) => value + 1)}
        >
          Refresh invitations
        </button>
      </section>
    </>
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
