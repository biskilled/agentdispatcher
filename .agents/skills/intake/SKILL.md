---
name: intake
description: Turn design / spec / PRD documents into tracked use cases and work items
  in AgentDesk, then hand off to solve. Use this whenever the user wants to plan a
  project from documents, "process my design docs", "build from my spec", turn a PRD
  or design doc into tasks/use cases, intake requirements, or "set up the backlog
  from my docs". Reads the project's document folder, maps each loose doc to one use
  case with its work items, creates them in AgentDesk, and writes a tracked use-case
  MD (embedding the source verbatim) into use_cases/ WITHOUT ever moving or deleting
  the original doc. Do NOT use for editing code directly (use the build/solve skill)
  or for non-planning requests.
allowed-tools:
- Read
- Glob
- Write
- mcp__create_entity
- mcp__list_work_items
- mcp__get_item_by_number
- mcp__run_work_item_pipeline
---

# Intake — documents → use cases → solve

You turn the project's **design documents** into a tracked backlog in AgentDesk, with no
command needed. Each loose document becomes **one use case** with its **work items**, and the
document is filed under `use_cases/` so it's tracked from then on.

## 1. Find the document folder

The docs live in the project's document folder — default `documents/` (an admin may have set a
different folder in AgentDesk → Settings → Project → Document folder; if you were told a
`doc_dir`, use that). Inside it:
- `use_cases/` (inside that folder) — **already tracked** (skip these).
- Any other `.md` files — **loose docs** to intake.
- `.errors/` (inside that folder) — files that previously failed (report, don't reprocess).

List the loose `.md` files (not under `use_cases/`, not dotfiles/underscore files). If there are
none, tell the user there's nothing to intake and stop.

## 2. Map each loose doc → one use case + items

For **each** loose document, read it in full, then extract:
- **use case**: a short name + a 1-2 sentence summary of what the doc describes.
- **items**: 4-12 concrete, implementable work items. Each item has a name and a type —
  one of `feature`, `bug`, `task`, or `requirement`. Keep names short and specific.

Create them in AgentDesk with `mcp__create_entity`:
1. `create_entity(category="use_case", name=<use case name>, description=<summary>)` — capture the
   returned use-case **UUID**.
2. For each item: `create_entity(category=<type>, name=<item name>, description=<detail>, parent_id=<use-case UUID>)`.

Then create the use-case MD under `use_cases/` **inside the same document folder you read the loose
docs from** — i.e. `<doc_dir>/use_cases/<slug>.md`, honouring the project's configured `doc_dir` (an
absolute external folder when the user set one; only fall back to a local `documents/use_cases/` when
no `doc_dir` is configured). **Do NOT scaffold a `documents/` folder inside the code repo when
`doc_dir` points elsewhere.** Embed the **original document verbatim at the top** (under a
`## Source document` heading) followed by the Summary / Requirements / Action Items scaffold.
**Never move or delete the source doc** — leave it exactly where it is; it stays as the record of
what the user wrote. If a doc can't be parsed, leave it and note it as an error — do not guess.

## 3. Report + hand off to solve

Summarise what you created: N use cases, M items, per document. Then:
- Created items are **unapproved** (no `wi_id` yet) — the human reviews and approves them in the
  AgentDesk **Planning** tab. Tell the user to approve the ones they want built.
- **Only when the user asks to build/solve** (or has already approved items): run the build.
  For each approved, open item under an approved use case, call
  `mcp__run_work_item_pipeline(work_item_id=<uuid>)` (the PM → Architect → Developer → Reviewer
  pipeline — this is "solve" for one item). Do the items in priority order; report progress.

Never auto-run the pipeline on unapproved items — approval is the human gate. Never fabricate
docs or items that aren't in the source; if a doc is thin, create fewer items and say so.

## Output

When done, report exactly: which docs were intaken, the use cases + item counts created, which
were moved to `use_cases/`, any errors, and the next step ("approve in Planning, then say 'solve'").