import { useEffect, useState, type FormEvent } from "react";
import { api } from "./api";

type Policy = { attribution_days: number | null; revision: number };

/** Make irreversible attribution expiry explicit; financial evidence is retained separately. */
export function RetentionSettings({ tenant, report }: {
  tenant: string; report: (message: string) => void;
}) {
  const [policy, setPolicy] = useState<Policy | null>(null);
  const [days, setDays] = useState("");
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    let active = true;
    setPolicy(null);
    api<Policy>("/retention", tenant).then((value) => {
      if (active) { setPolicy(value); setDays(value.attribution_days?.toString() ?? ""); }
    }).catch((error) => { if (active) report(error.message); });
    return () => { active = false; };
  }, [tenant]);
  async function save(event: FormEvent) {
    event.preventDefault();
    if (!policy || saving) return;
    setSaving(true);
    try {
      const value = await api<Policy>("/retention", tenant, { method: "PUT", body: JSON.stringify({
        revision: policy.revision, attribution_days: days ? Number(days) : null,
      }) });
      setPolicy(value);
      report(value.attribution_days ? "Attribution expiry enabled for future worker runs." : "Automatic attribution expiry disabled.");
    } catch (error) { report((error as Error).message); }
    finally { setSaving(false); }
  }
  return <section className="panel form-panel">
    <h2>Attribution retention</h2>
    <p>
      Automatic expiry is disabled by default. When enabled, the worker removes
      older user, session, trace, job, project, work-item and configuration attribution
      from usage and overlapping observations. Charges, token measurements, pricing
      evidence and replay protection remain. Historical attribution cannot be restored
      by disabling this policy. Choose a horizon that covers your reporting needs.
    </p>
    <form className="inline-form" onSubmit={save}>
      <label>Keep attribution for days (blank disables expiry)
        <input type="number" min="1" max="36500" disabled={!policy || saving} value={days} onChange={(event) => setDays(event.target.value)} />
      </label>
      <button className="primary" disabled={!policy || saving}>Apply retention policy</button>
    </form>
    <p className="muted">This expires usage attribution, not all workspace records. Complete workspace deletion is an offline operator action.</p>
  </section>;
}
