import { useState } from "react";

/** Describe each supported connection without implying telemetry can route model calls. */
export function SourceSetup() {
  const [source, setSource] = useState("sdk");
  return (
    <section className="panel form-panel">
      <h2>Connect a reporting source</h2>
      <label>
        Source type
        <select value={source} onChange={(event) => setSource(event.target.value)}>
          <option value="sdk">Application or scheduled job</option>
          <option value="mcp">Local MCP server</option>
          <option value="codex">Codex</option>
          <option value="claude">Claude Code</option>
          <option value="gateway">LiteLLM gateway</option>
        </select>
      </label>
      <p>
        Create a dedicated key for the application and environment in SDK keys (or LLM keys for gateway routing).
        Keep the secret in the source application's secret store. Send a test
        request, then check the source and delivery tables below.
      </p>
      {source === "sdk" && (
        <p>
          Install agentdispatcher-sdk in the application. Wrap its HTTP/provider
          client and scheduled jobs with Monitor. Carry export_context() through
          queue messages to retain the same job, session and work-item attribution.
        </p>
      )}
      {source === "mcp" && (
        <p>
          Launch services/mcp/proxy.py from your MCP client using an authorized
          local registration. It works on Mac, Windows and Linux. Keep upstream
          credentials separate; instrument owned servers to measure nested LLM
          calls. Tool counts alone cannot reveal those costs.
        </p>
      )}
      {source === "codex" && (
        <>
          <p>
            Codex 0.164.0 was verified with a local fixture. Configure its OTLP HTTP
            JSON log exporter for /api/otlp/v1/logs with a scoped SDK key. Match
            the emitted service name and environment; codex exec emits codex_exec.
            Keep prompt logging off. Check other versions before relying on coverage.
          </p>
          <p>
            Completed responses report tokens. Cost and request latency remain
            unknown where the CLI provides no evidence. This connection monitors
            usage and does not change model routing.
          </p>
        </>
      )}
      {source === "claude" && (
        <>
          <p>
            Enable Claude Code OTLP logs through an authenticated collector. Use
            its HTTP/protobuf receiver and a separate SDK key scoped to claude-code
            and your environment. Disable prompts, tool details, raw bodies and
            overlapping metrics/traces for this connection.
          </p>
          <p>
            Supported request/error records report tokens and available client
            cost estimates. They do not establish actual subscription charges.
            Official-format fixtures pass; live Claude provider traffic has not
            been verified. Model routing controls require a gateway connection.
          </p>
        </>
      )}
      {source === "gateway" && (
        <p>
          Start the optional LiteLLM service and register a gateway-purpose key.
          Route compatible API clients through that gateway to apply model policies.
          Use the gateway as the billing source; overlapping SDK observations must
          share its correlation identifiers instead of adding a second charge.
        </p>
      )}
      <p className="muted">
        A source that has never connected is not automatically discovered. Rejected
        records and stale delivery indicate coverage gaps; no report does not mean
        zero usage. Full setup examples are in integrations/cli and services/mcp.
      </p>
    </section>
  );
}
