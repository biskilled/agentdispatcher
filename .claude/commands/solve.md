---
allowed-tools:
- Read
- Write
- Glob
- Bash
- mcp__agentdesk_project__search_memory
- mcp__agentdesk_project__bootstrap_session
- mcp__agentdesk_project__list_work_items
- mcp__agentdesk_project__get_item_by_number
- mcp__agentdesk_project__update_work_item
- mcp__agentdesk_project__run_work_item_pipeline
- mcp__agentdesk_project__record_event
description: 'The build skill — gets work done at any SCOPE: a single item, one use
  case, all open use cases, or a direct task you type. Triggers on "solve", "build",
  "implement", "fix", "clear the backlog", "/solve". For each item it implements the
  smallest correct change (using the developer engine / work-item pipeline under the
  hood), verifies it, records the result, and updates status + score. Stops an item
  once its score is high enough, ends the run when the scope is complete (or the iteration
  budget is hit), and leaves the final "done" to human approval.

  '
---

# solve — clear the open backlog to "good enough"

You are an autonomous teammate that works the project's **open** work items until each
is in good shape, then hands them to the human for final approval. You do **not**
mark things `done` — you take them to `review` with a high score; the human approves.

> **CLI vs backend.** In a CLI (Claude Code / Codex / Gemini) you implement directly,
> using this skill. On the backend (no CLI), defer the heavy lifting to the
> **developer** skill / `run_work_item_pipeline` (PM → Architect → Developer → Reviewer),
> which writes acceptance criteria + plan and implements. Either way, the loop and the
> stop condition below are the same.

## 1. Load the backlog (first, always)

- `list_work_items` with status **active** → the open use cases and their open items.
- `bootstrap_session` for current project context (facts, conventions, recent work).
- If the user named a use case, scope to it; otherwise take the whole open set.

## 2. Order the work

Within the open set, work in this priority:
1. **bugs** (they block trust), then 2. **use_case** parents, then 3. **features**, then 4. **tasks** — and within a type, highest `score_importance` first. Finish a use case's children before moving to the next use case.

## 3. Solve each item (the loop)

> **Run against the RIGHT project first.** The work items you solve must be in the SAME
> AgentDesk project as the code you're editing. Before starting, confirm `list_work_items`
> actually returns items for THIS project — if it's empty, you're pointed at the wrong
> project (the code repo and the use cases are bound to different projects); stop and tell
> the user rather than "finding nothing to do."

For each open item, in order:
1. `get_item_by_number` → full detail: summary, **acceptance criteria**, implementation plan, parent use case.
2. `search_memory` with the task + stack tags → prior fixes, decisions, conventions. Don't repeat past mistakes.
3. **Implement the smallest correct change** that satisfies the acceptance criteria. Read the real code first; match the surrounding style and the project's `global.md` standards (clean code, no duplication, no hardcoded params).
4. **Verify** — run the project's tests / type-check / build. A change isn't solved until it's verified. Note what tests you added and how many ran / passed.
5. **Commit — and REFERENCE THE ITEM'S wi_id** so the commit is tracked against the work item. A commit whose message says `closes <WI_ID>` (or `fixes`/`resolves`) is hard-linked to that item AND moves it to review automatically. Example: `git commit -m "closes FE0002: add Power BI component extractor"`. Without the `closes <WI_ID>`, the work is invisible to the tracker. Push so the commit mirrors to the backend.
6. **Self-review** — read your own diff against the acceptance criteria and `global.md` (clean code, no duplication, no hardcoded params/secrets, tests present and passing). Record the outcome (passed / issues found + fixed).
7. `update_work_item` → set `user_status` to **`review`** and a high `score_status` (4–5) when the acceptance criteria are met, verified, and self-reviewed. **Never leave a solved item at its old score** — always advance it. If you can't solve it (missing info, external blocker), set `user_status` **`blocked`** with a note and move on — never silently skip.
8. `record_event` → the durable lesson (root cause / pattern + tags) so the next session benefits.
9. `record_work_log` (`kind='item'`, `wi_id`, short `summary`, `tests_added`, `code_review`, `score`) → a one-line record of what you did on THIS item. Passing `score`/`status` here also advances the item, so its state and the log never disagree.

### Scoring & when to stop working an item
- **Score high enough → stop** that item (leave it at `review` for the human). "High enough" = acceptance criteria met **and** verified (tests pass), not just "code written."
- If two attempts don't raise the score, mark it `blocked` with the reason rather than thrash.

### After each use case (its children are done)
`record_work_log` with `kind='use_case'` (the use case's wi_id) and a fuller **summary**: what was built overall, `tests_added` + `tests_run` + `tests_passed`, the `code_review` outcome, the final `score`, and `duration_min`. This renders into the use case's `## Work Log` MD section (with its hard-linked commits) — the human's record of what was done, when, and how long it took.

## 4. Stop the run when

- no open items remain, **or**
- everything left is `blocked`, **or**
- you hit the iteration/budget cap for this session.

Then summarize: what you took to `review`, what's `blocked` and why.

## 5. After the run

- Memory regenerates automatically — items you moved out of "open" drop out of `OPEN_ITEMS.md` / CLAUDE.md, and new facts you recorded appear in `FACTS.md`.
- The **human approves** the use cases to complete them (that's the `done` transition); on approval the memory files update again to reflect the new current state.

That's the contract: **you clear the backlog to review with high scores and clean memory; the human approves.**
