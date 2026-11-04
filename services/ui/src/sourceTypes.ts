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
    id: "gateway",
    label: "LLM gateway",
    description:
      "Start here for LLM calls. LiteLLM routes requests from your applications, schedulers and compatible coding tools, and automatically reports model usage to this workspace.",
  },
  {
    id: "sdk",
    label: "Applications & jobs",
    description:
      "Route an application's LLM calls through the gateway first. Add SDK reporting only for job start/finish, heartbeats, non-LLM API calls or existing requests that bypass the gateway.",
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
      "Use a LiteLLM gateway key to route and monitor supported Codex model calls. Direct telemetry below is an alternative for installations that keep their existing model connection; do not report the same calls twice.",
  },
  {
    id: "claude",
    label: "Claude Code",
    description:
      "Use a LiteLLM gateway key to route and monitor supported Claude Code model calls. Direct telemetry below is an alternative for installations that keep their existing model connection; do not report the same calls twice.",
  },
  {
    id: "mcp",
    label: "MCP servers",
    description:
      "Monitor calls to an MCP server. Create its reporting credential here, then configure the local proxy or instrument the server.",
  },
  {
    id: "status",
    label: "Reporting status",
    description:
      "Check which sources send usage, when they last reported, and whether exports were rejected. A saved connection alone does not prove that data is arriving.",
  },
];
