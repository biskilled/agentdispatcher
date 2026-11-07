import collector from "../../../packaging/collector/downloads.json";

/** Connect account measurements through one local package containing the upstream reader. */
export function AccountSetup() {
  return (
    <section className="panel form-panel">
      <h2>Connect CLI subscription accounts</h2>
      <p>
        See subscription limits, reset times, balances and provider-reported
        spending. Calls sent through the LiteLLM gateway are already monitored;
        this optional collector adds account information.
      </p>
      <ol>
        <li>
          Add a connection below for this device or user and save its sync key.
        </li>
        <li>
          <a className="secondary" href={collector.url}>
            Download AgentDispatcher Collector
          </a>
          <p>
            Version {collector.version} · {collector.platform}. One download
            includes the account reader and its runtime. No separate CodexBar,
            Python or Dispatcher SDK installation is needed.
          </p>
        </li>
        <li>
          Unzip the download, open a terminal in its folder, and run:
          <pre>{`./AgentDispatcherCollector --configure\n./AgentDispatcherCollector --interval 300`}</pre>
          <p>
            Enter this app address ({window.location.origin}) and the CLI
            account sync key when prompted. The key is saved in an owner-only
            local file.
          </p>
        </li>
      </ol>
      <p>
        This is an additional account reader, not a replacement for Codex,
        Cursor, Claude Code or other coding tools. It does not run your prompts
        or change those tools. Provider sign-in may be required on the device
        holding your accounts; the browser cannot access another machine's
        sessions.
      </p>
      <details>
        <summary>Collection options</summary>
        <p>
          The second command checks every 300 seconds while it is running.
          Ctrl-C stops it. Omit --interval for one check, or use your scheduler
          to run it periodically. It does not install an automatic startup
          service.
        </p>
        <p>
          Add --provider codex (or another supported provider ID) to choose one
          reader. Use --reader --help for reader options. Existing reader
          preferences are honored. DISPATCHER_URL and DISPATCHER_ACCOUNT_KEY can
          override saved configuration in managed environments.
        </p>
      </details>
      <p>
        Provider credentials stay on your device. Only selected account
        measurements and display labels are sent here. Missing readings remain
        unknown. Account balances do not add request charges or provide per-call
        token attribution.
      </p>
      <p className="muted">
        This release is ad-hoc signed, not Apple notarized; macOS may require
        approval in Privacy &amp; Security.{" "}
        <a href={collector.checksum_url}>Verify the download checksum</a>.
        Native Windows collection is not included; you can view synced accounts
        from Windows or mobile browsers. Credits: CodexBar by Peter Steinberger
        and contributors (MIT), Python (PSF), and PyInstaller (bootloader
        redistribution exception). Licenses are included in the download.
      </p>
    </section>
  );
}
