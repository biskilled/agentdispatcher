export const credentialSources = [
  { id: "sdk", label: "Applications & jobs" },
  { id: "codex", label: "Codex" },
  { id: "claude", label: "Claude Code" },
  { id: "mcp", label: "MCP servers" },
] as const;

export type CredentialSource = (typeof credentialSources)[number]["id"];
export type SourceTab = CredentialSource | "api" | "gateway" | "status";

export const sourceTabs: {
  id: SourceTab;
  label: string;
  description: string;
}[] = [
  {
    id: "sdk",
    label: "Applications & jobs",
    description:
      "Connect an application such as AgentTrade to report API calls, LLM usage and scheduled jobs. Add a connection below, then install its credential in your application.",
  },
  {
    id: "api",
    label: "External APIs",
    description:
      "Add API accounts such as CoinGecko, configure their prices and quotas, and edit existing connections. Your application's SDK reports the calls; provider credentials stay in that application.",
  },
  {
    id: "codex",
    label: "Codex",
    description:
      "Connect a Codex installation to report CLI usage. Create its credential here, then configure the exporter on the machine running Codex.",
  },
  {
    id: "claude",
    label: "Claude Code",
    description:
      "Connect a Claude Code installation to report CLI usage. Create its credential here, then configure telemetry through your authenticated collector.",
  },
  {
    id: "mcp",
    label: "MCP servers",
    description:
      "Monitor calls to an MCP server. Create its reporting credential here, then configure the local proxy or instrument the server.",
  },
  {
    id: "gateway",
    label: "LLM gateway",
    description:
      "Connect an application's model calls through LiteLLM. Create a gateway credential with allowed model names; provider credentials remain in the gateway configuration.",
  },
  {
    id: "status",
    label: "Reporting status",
    description:
      "Check which sources send usage, when they last reported, and whether exports were rejected. A saved connection alone does not prove that data is arriving.",
  },
];
