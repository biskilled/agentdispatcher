import { useRef, useState, type KeyboardEvent } from "react";
import { type Key, type Plan } from "./api";
import { CatalogView } from "./Accounting";
import { CoverageView } from "./Coverage";
import { SourceKeys } from "./SourceKeys";
import { AccountSetup } from "./AccountSetup";
import { AccountUsage } from "./AccountUsage";
import { GatewaySetup } from "./GatewaySetup";
import {
  credentialSources,
  sourceTabs,
  type CredentialSource,
  type SourceTab,
} from "./sourceTypes";

/** Keep each source's explanation and management controls together. */
export function SourcesView({
  tenant,
  admin,
  keys,
  gatewayKeys,
  plans,
  refresh,
  report,
  revision,
}: {
  tenant: string;
  admin: boolean;
  keys: Key[];
  gatewayKeys: Key[];
  plans: Plan[];
  refresh: () => void;
  report: (message: string) => void;
  revision: number;
}) {
  const [selected, setSelected] = useState<SourceTab>("gateway");
  const tabs = useRef<HTMLDivElement>(null);
  const [advancedSource, setAdvancedSource] = useState<CredentialSource>("sdk");
  function move(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const steps: Record<string, number> = { ArrowRight: 1, ArrowLeft: -1 };
    const next =
      event.key === "Home"
        ? 0
        : event.key === "End"
          ? sourceTabs.length - 1
          : event.key in steps
            ? (index + steps[event.key] + sourceTabs.length) % sourceTabs.length
            : null;
    if (next === null) return;
    event.preventDefault();
    setSelected(sourceTabs[next].id);
    tabs.current
      ?.querySelectorAll<HTMLButtonElement>('[role="tab"]')
      [next].focus();
  }
  return (
    <>
      <div
        className="source-tabs"
        role="tablist"
        aria-label="Source types"
        ref={tabs}
      >
        {sourceTabs.map((item, index) => (
          <button
            key={item.id}
            role="tab"
            id={`source-tab-${item.id}`}
            aria-selected={selected === item.id}
            aria-controls={`source-panel-${item.id}`}
            tabIndex={selected === item.id ? 0 : -1}
            onKeyDown={(event) => move(event, index)}
            onClick={() => setSelected(item.id)}
          >
            {item.label}
          </button>
        ))}
      </div>
      <div
        key={selected}
        role="tabpanel"
        id={`source-panel-${selected}`}
        aria-labelledby={`source-tab-${selected}`}
      >
        {!admin ? (
          <p className="notice">
            A workspace owner or administrator can manage connections. Your
            Overview shows the usage you have permission to view.
          </p>
        ) : selected === "api" ? (
          <CatalogView
            tenant={tenant}
            plans={plans}
            refresh={refresh}
            report={report}
          />
        ) : selected === "gateway" ? (
          <>
            <GatewaySetup tenant={tenant} revision={revision} />
            <SourceKeys
              tenant={tenant}
              source="gateway"
              keys={gatewayKeys}
              refresh={refresh}
              report={report}
            />
          </>
        ) : (
          <>
            <AccountSetup />
            <SourceKeys
              tenant={tenant}
              source="codexbar"
              keys={keys.filter((key) => key.source_type === "codexbar")}
              refresh={refresh}
              report={report}
            />
            <AccountUsage tenant={tenant} revision={revision} />
          </>
        )}
      </div>
      {admin && selected !== "accounts" && (
        <details className="panel form-panel">
          <summary>
            Advanced reporting: jobs, direct CLI telemetry &amp; MCP tools
          </summary>
          <p>
            Optional. Gateway LLM calls already report automatically. Use
            reporting credentials only for job lifecycle, non-LLM APIs, direct
            CLI telemetry, or MCP tool-call counts.
          </p>
          <p>
            An MCP server you own routes its internal LLM calls through the
            gateway like any other app. The gateway URL is not an MCP server
            URL. Tool-call instrumentation cannot reveal hidden LLM usage inside
            a third-party server.
          </p>
          <label>
            Reporting type
            <select
              value={advancedSource}
              onChange={(event) =>
                setAdvancedSource(event.target.value as CredentialSource)
              }
            >
              {credentialSources
                .filter((item) => item.id !== "codexbar")
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
            </select>
          </label>
          <SourceKeys
            key={advancedSource}
            tenant={tenant}
            source={advancedSource}
            keys={keys.filter(
              (key) => (key.source_type || "sdk") === advancedSource,
            )}
            refresh={refresh}
            report={report}
          />
        </details>
      )}
      <details className="panel form-panel">
        <summary>Reporting diagnostics</summary>
        <CoverageView tenant={tenant} report={report} revision={revision} />
      </details>
    </>
  );
}
