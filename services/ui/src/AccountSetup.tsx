import collectorUrl from "../../../packages/sdk/src/agentdispatcher_sdk/codexbar.py?url";

/** Explain optional account collection with one reader and a dependency-free uploader. */
export function AccountSetup() {
  return (
    <section className="panel form-panel">
      <h2>Connect CLI subscription accounts</h2>
      <p>
        Use this for subscription limits, reset times, balances and
        provider-reported spending. If your tool already sends LLM calls through
        the gateway, those calls are monitored automatically; this setup is
        optional account information.
      </p>
      <p>
        Account collection runs on the machine holding your provider sessions.
        We reuse CodexBar's open-source account readers for supported providers,
        including Codex, Claude, Cursor and Copilot. Your browser cannot read
        sessions on another machine. No Dispatcher desktop app is required.
      </p>
      <ol>
        <li>
          Install the{" "}
          <a
            href="https://github.com/steipete/CodexBar/blob/main/docs/cli.md"
            target="_blank"
            rel="noreferrer"
          >
            CodexBar CLI
          </a>{" "}
          on that machine, unless you already have it. Enable and authenticate
          the providers you use. CodexBar is the account-reading dependency for
          this integration.
        </li>
        <li>
          Add one connection below for that device or user and save its sync
          key.
        </li>
        <li>
          <a
            className="secondary"
            href={collectorUrl}
            download="dispatcher-account-sync.py"
          >
            Download account sync script
          </a>
          <p>
            Run the downloaded script with Python 3.12 or newer. It uses only
            Python's standard library: no Dispatcher SDK, repository clone or
            pip packages.
          </p>
        </li>
      </ol>
      <details>
        <summary>Sync command and environment variables</summary>
        <p>
          Set these variables in your shell or scheduler. The sync key comes
          from this tab's Add connection, not from the LLM gateway or a
          provider.
        </p>
        <pre>{`export DISPATCHER_URL="${window.location.origin}"\nexport DISPATCHER_ACCOUNT_KEY="<CLI account sync key>"\n\npython3 dispatcher-account-sync.py --interval 300`}</pre>
        <p>
          Run from the folder where you saved the script. Keep keys in your
          secret environment. DISPATCHER_URL is the public app address without
          /llm/v1.
        </p>
        <p>
          Omit --interval to sync once. Enabled providers come from CodexBar;
          --provider selects one. Existing CodexBar JSON exports can be sent
          with --file, without invoking CodexBar on the uploading machine.
        </p>
      </details>
      <p>
        Provider credentials stay on your device. Only selected account
        measurements and display labels are sent here. Failed readings are
        unavailable; missing measurements remain unknown. Account balances do
        not add request charges.
      </p>
      <p className="muted">
        The account reader currently uses upstream macOS/Linux runtimes; native
        Windows collection is not included. View synced accounts from any
        browser, including Windows and mobile. Credits: CodexBar by Peter
        Steinberger and contributors (MIT).
      </p>
    </section>
  );
}
