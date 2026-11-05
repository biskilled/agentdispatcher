import { useEffect, useState, type FormEvent } from "react";
import { api, type Key } from "./api";

type Routing = {
  aliases: Record<string, string>;
  default_model: string | null;
  allowed_models: string[];
  revision: string;
};
type Service = { name: string; model: string; id: string };

/** Edit native LiteLLM service aliases without changing the app's key or permissions. */
export function GatewayRouting({
  tenant,
  connection,
  close,
  report,
}: {
  tenant: string;
  connection: Key;
  close: () => void;
  report: (message: string) => void;
}) {
  const [routing, setRouting] = useState<Routing | null>(null);
  const [services, setServices] = useState<Service[]>([]);
  const [defaultModel, setDefaultModel] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const endpoint = `/gateway/keys/${connection.id}/routing`;
  useEffect(() => {
    let active = true;
    api<Routing>(endpoint, tenant)
      .then((value) => {
        if (!active) return;
        setRouting(value);
        setDefaultModel(value.default_model || "");
        setServices(
          Object.entries(value.aliases).map(([name, model]) => ({
            name,
            model,
            id: crypto.randomUUID(),
          })),
        );
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [endpoint, tenant]);

  async function save(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!routing || busy) return;
    const aliases = Object.fromEntries(
      services.map(({ name, model }) => [name.trim(), model]),
    );
    if (Object.keys(aliases).length !== services.length) {
      setError("Each service needs a unique name.");
      return;
    }
    setBusy(true);
    setError("");
    try {
      await api<Routing>(endpoint, tenant, {
        method: "PUT",
        body: JSON.stringify({
          aliases,
          default_model: defaultModel || null,
          revision: routing.revision,
        }),
      });
      report("Services and default saved. Your app key stays the same.");
      close();
    } catch (reason) {
      setError((reason as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function change(id: string, field: "name" | "model", value: string) {
    setServices((rows) =>
      rows.map((row) => (row.id === id ? { ...row, [field]: value } : row)),
    );
  }

  return (
    <section className="panel form-panel" aria-label="Gateway routing">
      <h2>Services &amp; default · {connection.name}</h2>
      <p>
        Give your app a service name such as trade-analysis. Each target is an
        allowed LiteLLM model name, which selects the provider, model and
        credentials configured on the gateway. Renaming a service does not
        change the app identity or its usage history.
      </p>
      {error && <p role="alert">{error}</p>}
      {!routing ? (
        <p>{error ? "Close and reopen to retry." : "Loading services…"}</p>
      ) : (
        <form onSubmit={save}>
          <fieldset className="gateway-routing-fields" disabled={busy}>
            <legend>Model routing</legend>
            <label>
              Default provider / model
              <select
                value={defaultModel}
                onChange={(event) => setDefaultModel(event.target.value)}
              >
                <option value="">No default — reject unrecognized names</option>
                {routing.allowed_models.map((model) => (
                  <option key={model} value={model}>
                    {model}
                  </option>
                ))}
              </select>
            </label>
            <p>
              An unrecognized name uses this default. Recognized allowed models
              keep their own route. Provider errors do not trigger this default.
              Your app must still send a model name.
            </p>
            {services.map((service, index) => (
              <div className="inline-form" key={service.id}>
                <label>
                  Service name {index + 1}
                  <input
                    required
                    maxLength={100}
                    pattern="[A-Za-z0-9][A-Za-z0-9._\/\-]*"
                    value={service.name}
                    onChange={(event) =>
                      change(service.id, "name", event.target.value)
                    }
                  />
                </label>
                <label>
                  Target model {index + 1}
                  <select
                    required
                    value={service.model}
                    onChange={(event) =>
                      change(service.id, "model", event.target.value)
                    }
                  >
                    <option value="">Choose an allowed model</option>
                    {routing.allowed_models.map((model) => (
                      <option key={model} value={model}>
                        {model}
                      </option>
                    ))}
                  </select>
                </label>
                <button
                  type="button"
                  className="text-button"
                  aria-label={`Remove service ${index + 1}`}
                  onClick={() =>
                    setServices((rows) =>
                      rows.filter((row) => row.id !== service.id),
                    )
                  }
                >
                  Remove
                </button>
              </div>
            ))}
            <div className="inline-form">
              <button
                type="button"
                className="secondary"
                disabled={services.length >= 100}
                onClick={() =>
                  setServices((rows) => [
                    ...rows,
                    { id: crypto.randomUUID(), name: "", model: "" },
                  ])
                }
              >
                Add service
              </button>
              <button className="primary">Save services</button>
            </div>
          </fieldset>
        </form>
      )}
      <button
        type="button"
        className="text-button"
        disabled={busy}
        onClick={close}
      >
        Close services
      </button>
    </section>
  );
}
