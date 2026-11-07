import { type GatewayConnection } from "./gatewayConnection";

const statusText: Record<GatewayConnection["state"], string> = {
  not_configured:
    "The operator needs to configure the LiteLLM gateway connection.",
  unavailable:
    "LiteLLM could not be reached. Check the gateway service and its credentials, then refresh.",
  no_models:
    "LiteLLM is reachable, but no models are configured. The operator must add provider credentials and models in LiteLLM before requests can run.",
  ready:
    "LiteLLM is reachable. Model availability is checked without making a paid request.",
};

/** Explain routing using the same catalog shown by the key form. */
export function GatewaySetup({
  connection,
  error,
}: {
  connection: GatewayConnection | null;
  error: string;
}) {
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
          <div className="source-intro">
            <h3>Set up your app in three steps</h3>
            <ol>
              <li>
                <strong>Configure a provider route in LiteLLM.</strong> The
                gateway stores the real provider API key and model. A route such
                as <code>{connection.models[0] || "configured-model"}</code>{" "}
                selects that provider/model. The app never needs the provider's
                key.
              </li>
              <li>
                <strong>Add an LLM key below.</strong> Choose its allowed
                providers/models and save the generated Dispatcher LLM key.
                Application and environment labels are optional. This key
                identifies the tenant and application scope, even when all apps
                share the same gateway URL.
              </li>
              <li>
                <strong>Open that connection's Services &amp; default.</strong>{" "}
                Add a service named <code>trade-analysis</code> and select its
                target route. Optionally select a default provider/model route,
                then save. Your app can keep the same service name when you
                change its target here.
              </li>
            </ol>
          </div>
          <details>
            <summary>Application setup</summary>
            <p>
              After saving the example service above, set these variables in
              your app's environment or secret store. The key is the
              <strong> Dispatcher LLM key generated here</strong>, not an
              OpenAI, Anthropic or other provider API key.
            </p>
            <pre>{`DISPATCHER_LLM_BASE_URL=${connection.base_url}\nDISPATCHER_LLM_KEY=<Dispatcher key from Add connection>\nDISPATCHER_SERVICE=trade-analysis`}</pre>
            <pre>{`import os\nfrom openai import OpenAI\n\n# The OpenAI-compatible client talks to Dispatcher.\nclient = OpenAI(\n    base_url=os.environ["DISPATCHER_LLM_BASE_URL"],\n    api_key=os.environ["DISPATCHER_LLM_KEY"],\n)\nresponse = client.chat.completions.create(\n    model=os.environ["DISPATCHER_SERVICE"],  # Saved service name\n    messages=[{"role": "user", "content": "Your request"}],\n)\nprint(response.choices[0].message.content)`}</pre>
            <p>
              The Python example uses the OpenAI client as an HTTP client; the
              actual provider can be any compatible route configured in LiteLLM.
              It requires the openai package in your app, but no Dispatcher SDK.
              If your existing app uses OPENAI_BASE_URL and OPENAI_API_KEY, set
              them to the same gateway URL and Dispatcher key respectively.
            </p>
            <p>
              In your existing YAML, put the saved service name in the model
              field your app sends to the gateway. Configure your shared client
              to use the gateway URL and Dispatcher key from the environment.
              The same configuration works for user requests and scheduled jobs.
            </p>
            <h3>YAML configuration example</h3>
            <p>
              Map these fields into your app's existing configuration loader.
              The *_env fields name environment variables; they are references,
              not literal credentials and are not expanded automatically by
              YAML.
            </p>
            <pre>{`llm:\n  base_url_env: DISPATCHER_LLM_BASE_URL\n  api_key_env: DISPATCHER_LLM_KEY\n  model: trade-analysis`}</pre>
            <p>
              The Python example above reads those same URL/key variables and
              sends the service name from DISPATCHER_SERVICE. If your YAML
              loader supplies model, pass that value to the client's model
              argument instead.
            </p>
            <h3>What does the model field select?</h3>
            <ul>
              <li>
                <strong>Service name:</strong> trade-analysis uses the target
                saved under Services &amp; default.
              </li>
              <li>
                <strong>Allowed route name:</strong> sends directly to that
                configured provider/model route.
              </li>
              <li>
                <strong>Unrecognized name:</strong> uses this connection's
                default, if one is configured; otherwise it is rejected.
              </li>
            </ul>
            <p>
              A model/service name is required even with a default. The default
              applies to unrecognized names, not provider errors or missing
              fields. Renaming a connection label does not rename its services.
              Optional user/job metadata adds attribution; the SDK is only
              needed for extra job lifecycle events or other API usage.
            </p>
          </details>
          <details>
            <summary>Operator setup: real provider key and model</summary>
            <p>
              For this repository's supplied gateway template, set the following
              variables on the <strong>gateway service</strong> and redeploy it:
            </p>
            <pre>{`LLM_PROVIDER_MODEL=<LiteLLM provider/model identifier>\nLLM_API_KEY=<real API key issued by that provider>`}</pre>
            <p>
              The supplied template exposes this as configured-model. For
              multiple providers/models, define additional routes in LiteLLM.
              Provider credentials stay in the gateway's secret configuration;
              they are not the Dispatcher keys issued below.
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
        populate this workspace. Confirm received requests in Reporting
        diagnostics below.
      </p>
    </section>
  );
}
