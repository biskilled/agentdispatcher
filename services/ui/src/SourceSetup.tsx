import { sourceTabs, type SourceTab } from "./sourceTypes";

/** Explain a source before its inline controls; technical instructions stay optional. */
export function SourceSetup({ source }: { source: SourceTab }) {
  const definition = sourceTabs.find((item) => item.id === source)!;
  return (
    <section className="source-intro">
      <h2>{definition.label}</h2>
      <p>{definition.description}</p>
      {!["api", "status"].includes(source) && (
        <details>
          <summary>Setup instructions</summary>
          {source === "sdk" && (
            <p>
              Install agentdispatcher-sdk in the application. Wrap its
              HTTP/provider client and scheduled jobs with Monitor. Carry
              export_context() through queue messages to retain the same job,
              session and work-item attribution.
            </p>
          )}
          {source === "mcp" && (
            <p>
              Launch services/mcp/proxy.py from your MCP client using an
              authorized local registration. It works on Mac, Windows and Linux.
              Keep upstream credentials separate; instrument owned servers to
              measure nested LLM calls. Tool counts alone cannot reveal those
              costs.
            </p>
          )}
          {source === "codex" && (
            <>
              <p>
                Codex 0.164.0 was verified with a local fixture. Configure its
                OTLP HTTP JSON log exporter for /api/otlp/v1/logs with a scoped
                SDK key. Match the emitted service name and environment; codex
                exec emits codex_exec. Keep prompt logging off. Check other
                versions before relying on coverage.
              </p>
              <p>
                Completed responses report tokens. Cost and request latency
                remain unknown where the CLI provides no evidence. This
                connection monitors usage and does not change model routing.
              </p>
            </>
          )}
          {source === "claude" && (
            <>
              <p>
                Enable Claude Code OTLP logs through an authenticated collector.
                Use its HTTP/protobuf receiver and a separate SDK key scoped to
                claude-code and your environment. Disable prompts, tool details,
                raw bodies and overlapping metrics/traces for this connection.
              </p>
              <p>
                Supported request/error records report tokens and available
                client cost estimates. They do not establish actual subscription
                charges. Official-format fixtures pass; live Claude provider
                traffic has not been verified. Model routing controls require a
                gateway connection.
              </p>
            </>
          )}
          {source === "gateway" && (
            <p>
              Start the optional LiteLLM service and register a gateway-purpose
              key. Route compatible API clients through that gateway to apply
              model policies. Use the gateway as the billing source; overlapping
              SDK observations must share its correlation identifiers instead of
              adding a second charge.
            </p>
          )}
          <p className="muted">
            After configuring the application or CLI, send a test request and
            open Reporting status to verify delivery. Creating a credential does
            not install an exporter or discover local applications.
          </p>
        </details>
      )}
    </section>
  );
}
