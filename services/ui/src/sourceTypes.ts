export const credentialSources = [
  { id: "sdk", label: "Applications & jobs" },
  { id: "codex", label: "Codex" },
  { id: "claude", label: "Claude Code" },
  { id: "mcp", label: "MCP tool-call reporting" },
  { id: "codexbar", label: "CLI account sync" },
] as const;

export type CredentialSource = (typeof credentialSources)[number]["id"];
export type SourceTab = "gateway" | "accounts" | "api";

export const sourceTabs: { id: SourceTab; label: string }[] = [
  { id: "gateway", label: "Application LLM calls" },
  { id: "accounts", label: "CLI account usage" },
  { id: "api", label: "Other API usage" },
];
