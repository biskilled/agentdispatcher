import { useRef, useState, type KeyboardEvent } from "react";
import { type Key, type Plan } from "./api";
import { CatalogView } from "./Accounting";
import { CoverageView } from "./Coverage";
import { SourceKeys } from "./SourceKeys";
import { SourceSetup } from "./SourceSetup";
import { sourceTabs, type SourceTab } from "./sourceTypes";

/** Keep each source's explanation and management controls together. */
export function SourcesView({
  tenant,
  admin,
  keys,
  gatewayKeys,
  plans,
  refresh,
  report,
}: {
  tenant: string;
  admin: boolean;
  keys: Key[];
  gatewayKeys: Key[];
  plans: Plan[];
  refresh: () => void;
  report: (message: string) => void;
}) {
  const [selected, setSelected] = useState<SourceTab>(admin ? "sdk" : "status");
  const tabs = useRef<HTMLDivElement>(null);
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
        <SourceSetup source={selected} />
        {selected === "status" ? (
          <CoverageView tenant={tenant} report={report} />
        ) : !admin ? (
          <p className="notice">
            A workspace owner or administrator can add and manage connections.
            Reporting status shows the usage you have permission to view.
          </p>
        ) : selected === "api" ? (
          <CatalogView
            tenant={tenant}
            plans={plans}
            refresh={refresh}
            report={report}
          />
        ) : (
          <SourceKeys
            tenant={tenant}
            source={selected}
            keys={
              selected === "gateway"
                ? gatewayKeys
                : keys.filter((key) => (key.source_type || "sdk") === selected)
            }
            refresh={refresh}
            report={report}
          />
        )}
      </div>
    </>
  );
}
