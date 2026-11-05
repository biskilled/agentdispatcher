/** Explain one shared local sync path for all providers supported by the installed CodexBar. */
export function AccountSetup() {
  return (
    <section className="panel form-panel">
      <h2>Connect your CLI accounts with CodexBar</h2>
      <p>
        See subscription limits, reset times and available balances for Codex,
        Claude, Cursor, Copilot and other providers supported by your installed
        CodexBar. This reads account usage without changing how your tools call
        models.
      </p>
      <ol>
        <li>
          Install{" "}
          <a
            href="https://github.com/steipete/CodexBar#install"
            target="_blank"
            rel="noreferrer"
          >
            CodexBar and its CLI
          </a>{" "}
          on the machine that holds your provider sessions. Enable and
          authenticate the providers you use.
        </li>
        <li>
          Add one connection below for that device or user, then save its sync
          key.
        </li>
        <li>
          Install the Dispatcher SDK from this repository (
          <code>pip install ./packages/sdk</code>) and run the sync command on
          that machine.
        </li>
      </ol>
      <details>
        <summary>Sync command and environment variables</summary>
        <p>
          Set these variables in your shell or scheduler. DISPATCHER_URL is this
          app's public address, without /llm/v1. Keep keys out of source files.
        </p>
        <pre>{`DISPATCHER_URL=${window.location.origin}\nDISPATCHER_ACCOUNT_KEY=<connection key>\n\npython -m agentdispatcher_sdk.codexbar --interval 300`}</pre>
        <p>
          Without --interval it syncs once. Enabled providers are read from
          CodexBar; use --provider with a supported provider ID to select one.
          Existing JSON exports can be sent with --file.
        </p>
      </details>
      <p>
        Provider credentials stay on your device. Only selected account
        measurements and display labels are sent here. A failed provider appears
        as unavailable; unsupported or missing measurements stay unknown.
      </p>
      <p className="muted">
        CodexBar publishes macOS and Linux runtimes. Native Windows support is
        not provided by this integration. All reported accounts remain viewable
        here from any browser, including Windows and mobile.
      </p>
    </section>
  );
}
