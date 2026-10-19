---
name: rescan
description: 'Learn / re-index a whole project in one pass — built for a LARGE existing
  codebase you just joined, or a periodic re-alignment. Triggers on "rescan", "learn
  project", "index the codebase", "map the project", "re-align memory", "/rescan".
  Does a COMPLETE scan: maps the current code into project facts + use cases (deduping
  against what already exists), reconciles every active fact against current code,
  and checks that OPEN use cases/items still match the code — reversibly archiving
  records proven obsolete. A full rescan is EXPENSIVE (whole-codebase read + LLM analysis)
  — it warns first and reports the token/$ cost.

  '
allowed-tools:
- Read
- Glob
- Bash
- mcp__agentdesk_project__search_memory
- mcp__agentdesk_project__bootstrap_session
- mcp__agentdesk_project__list_work_items
- mcp__agentdesk_project__get_item_by_number
- mcp__agentdesk_project__update_work_item
- mcp__agentdesk_project__record_event
---

<!-- AgentDesk-only config (ignored by external CLIs). Declares how this skill runs.
     runtime: cli | backend | both  ·  api = the local-API-agent runtime (Electron), which
     drives the same steps via an LLM API instead of a CLI, choosing the provider below. -->
```agentdesk
runtime: both
default_provider: anthropic
api:
  # The local API-agent rescan (no CLI needed). One entry per supported API; the app uses
  # the selected provider's model + the user's locally-stored key. Same schema as other skills.
  enabled: true
  providers:
    anthropic:
      model: claude-opus-4-8
    openai:
      model: gpt-5
    google:
      model: gemini-2.5-pro
  max_steps: 60          # safety cap on agent tool-loop iterations
```

# rescan — learn / re-index a whole project in one pass

Use this to bootstrap memory for a **large existing project** (e.g. one you just joined via
"Join existing"), or to **re-align** an existing project's backlog with its code. It is a
COMPLETE, one-shot scan — not the light per-session update. Run it once after setup; re-run
periodically when the code has drifted from the tracked use cases.

> **CLI vs backend.**
> - In a **CLI** (Claude Code / Codex / Gemini): git is already synced and the code is on
>   disk — scan the LOCAL files directly (`list_dir`/`read_file`/`get_code_symbols`).
> - On the **backend** (no local files): the hosted server can't see the checkout, so it uses
>   a **server-side GitHub checkout** of the synced repo. Same steps below, same output.

## 0. Warn about cost — then confirm
A full rescan reads the whole codebase and runs LLM analysis, so it can be **expensive**.
Before starting: tell the user roughly what will be scanned (N files / M symbols) and that
it will consume tokens. Say they can watch the spend in **Settings → Billing → LLM Cost &
Usage** (and the top-bar usage widget). **Get an explicit "go ahead"** unless the user
already asked for a full rescan. Never silently run a large scan.

## 1. Load current state
- `bootstrap_session` — project facts, conventions, recent work.
- `list_work_items` (status **all**) — the existing use cases + items (with ids, dates, status).
- `search_memory` on the main feature areas — what memory already knows.
Hold this as the "before" picture so you can DEDUPE and DIFF against it (never re-create what
already exists).

## 2. Scan the code → build the map
- Walk the tree (`list_dir`) and read the significant files; use `get_code_symbols` for the
  function/class map per file.
- `get_commits` (recent) — what's changed lately and where the activity is (hotspots).
Produce: the module/architecture map, the stack, and the busiest areas.

## 3. Reconcile code → **facts** (authoritative, deduped)
Derive durable current project facts (stack, architecture decisions, key modules,
conventions) from the scan. Compare **every active fact** with current-code evidence:
- unchanged → keep one canonical fact;
- changed → write the current fact and supersede the old one;
- no longer true (for example SQLite was replaced by PostgreSQL) → expire/supersede it so
  it disappears from active memory and search.
Never physically delete fact history. Use AgentDesk's `valid_to`/supersession mechanism so
the reconciliation remains auditable and reversible.

## 4. Map code → **use cases** (only real gaps, never duplicates)
For each major feature/subsystem the code reveals:
1. Check `list_work_items` + `search_memory` for an existing use case that already covers it.
2. Only `create_entity(category="use_case", …)` for a genuinely **uncovered** area — with a
   short name + summary. Created items are **unapproved** (human approves in Planning).
**Do not** spawn a use case per file or per function — group by feature/subsystem. If in
doubt that it's new, don't create it.

## 5. Dedupe existing use cases / items
Scan the current backlog for **duplicates** (same or clearly-overlapping name/scope). For a
confirmed duplicate: keep the richer one, and `update_work_item` the other to merge/close it
(or mark it for the human). Never delete approved work silently — recommend + let the human
confirm the merge.

## 6. Alignment / obsolescence check (the important one)
For each **open** use case / item, decide if it's still relevant to the CURRENT code:
- Age: how old is it (`created_at`) and when was it last touched (`updated_at`)?
- Code drift: has its area of code changed since? Use `get_file_history` / `get_commits` on
  the files the item refers to, and `get_work_item_history` for the item's own trail.
- Age alone is never sufficient. Archive an open item only when current code directly proves
  that its described work is already implemented, the feature was removed, or the requirement
  no longer applies.
- A user-confirmed full Rescan authorizes **soft archival** of high-confidence obsolete items.
  Never hard-delete: retain IDs, history, commits and prompts, and report an undo reference.
- Keep uncertain items active and report why they could not be resolved.

## 7. Report + record
Summarize, in one place:
- scanned: N files / M symbols; hotspots.
- facts: X recorded / Y superseded.
- use cases: Z newly proposed (unapproved).
- duplicates: found / merged.
- facts: current / superseded / expired, with concrete evidence.
- obsolete open items: soft-archived / kept uncertain, with concrete evidence and undo reference.
- **cost**: the tokens / $ this rescan used (point them at Billing → LLM Cost & Usage).
Then `record_event` a short "rescan run" summary so the next session knows it happened.

## Guardrails
- **Confirm before an expensive run** and always surface the cost.
- **Dedupe, never duplicate** — check memory before creating anything.
- **Current code is authoritative during a confirmed full Rescan.** Supersede stale active facts.
- **Never hard-delete** facts, use cases or items. Soft-archive only high-confidence obsolete
  records, preserve audit history, and make the reconciliation undoable.
- **Group by feature**, not by file — a rescan should not explode the backlog.