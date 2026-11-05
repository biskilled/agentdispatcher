import { useEffect, useState } from "react";
import { api } from "./api";

type Connection = {
  base_url: string;
  state: "not_configured" | "unavailable" | "no_models" | "ready";
  models: string[];
};

const statusText: Record<Connection["state"], string> = {
  not_configured:
    "The operator needs to configure the LiteLLM gateway connection.",
  unavailable:
    "LiteLLM could not be reached. Check the gateway service and its credentials, then refresh.",
  no_models:
    "LiteLLM is reachable, but no models are configured. The operator must add provider credentials and models in LiteLLM before requests can run.",
  ready:
    "LiteLLM is reachable. Model availability is checked without making a paid request.",
};

/** Read connection details from LiteLLM; clients need no separate usage exporter. */
export function GatewaySetup({
  tenant,
  revision,
}: {
  tenant: string;
  revision: number;
}) {
  const [connection, setConnection] = useState<Connection | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let active = true;
    setConnection(null);
    setError("");
    api<Connection>("/gateway/connection", tenant)
      .then((value) => {
        if (active) setConnection(value);
      })
      .catch((reason: Error) => {
        if (active) setError(reason.message);
      });
    return () => {
      active = false;
    };
  }, [tenant, revision]);

  return (
    <section className="panel form-panel gateway-setup">
      <h2>Connect once through LiteLLM</h2>
      <p>
        Create an LLM key below, then set the gateway address and key in your
        application or coding tool. Requests through this gateway report usage
        automatically. No SDK or CLI telemetry connection is required for these
        LLM calls.
      </p>
      {error ? (
        <p role="alert">{error}</p>
      ) : !connection ? (
        <p>Checking gateway…</p>
      ) : (
        <>
          <p role="status">{statusText[connection.state]}</p>
          <label>
            Gateway API base URL
            <input readOnly value={connection.base_url} />
          </label>
          {!!connection.models.length && (
            <p>
              Configured model names:{" "}
              <strong>{connection.models.join(", ")}</strong>
            </p>
          )}
          <details>
            <summary>Application setup</summary>
            <p>
              Set these environment variables in your app. Use the new LLM key
              and one of its allowed model names.
            </p>
            <pre>{`OPENAI_BASE_URL=${connection.base_url}\nOPENAI_API_KEY=<your LLM key>\nLLM_MODEL=<allowed model name>`}</pre>
            <pre>{`import os\nfrom openai import OpenAI\n\nclient = OpenAI()\nresponse = client.chat.completions.create(\n    model=os.environ["LLM_MODEL"],\n    messages=[{"role": "user", "content": "Your request"}],\n)`}</pre>
            <p>
              The same client works in user requests and scheduled jobs.
              Optional request metadata can identify a user, project or job; use
              the SDK only when you also need job lifecycle events or other API
              usage.
            </p>
          </details>
        </>
      )}
      <details>
        <summary>Coding tools and enterprise rollout</summary>
        <p>
          Use a supported tool's gateway mode with an LLM key and allowed model.
          Administrators can distribute client configuration to managed
          machines; adding a key here does not configure installations
          automatically.
        </p>
        <p>
          <a
            href="https://docs.litellm.ai/docs/proxy/client_setup/overview"
            target="_blank"
            rel="noreferrer"
          >
            LiteLLM client setup: Codex, Claude Code, Copilot and other tools
          </a>
          . Tool and version support varies; existing subscriptions are not
          automatically used by a gateway connection.
        </p>
      </details>
      <p className="muted">
        Provider credentials and model definitions are managed once in LiteLLM.
        AgentDispatcher uses its native virtual keys and usage callbacks to
        populate this workspace. Confirm received requests in Reporting diagnostics below.
      </p>
    </section>
  );
}
