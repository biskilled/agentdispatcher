---
description: Discover agent skills from the open skills.sh ecosystem when the user
  asks "how do I do X", "find a skill for X", or wants a capability that might already
  exist as an installable skill. Searches the community registry, ranks candidates
  by install counts and source reputation, then hands installation off to AgentDesk's
  governed External Skills flow — it NEVER installs skills directly. Do NOT use for
  building features yourself (use solve) or for skills that already exist in this
  project.
---

# Find skills — discover from the open ecosystem, install through AgentDesk

You help the user find existing community skills instead of reinventing them.
Discovery is open; **installation is governed** — every skill enters this
project only through AgentDesk's External Skills review flow, never via a
direct install command.

## 1. When to activate

- The user asks "how do I do X" and X is a common, tool-shaped task
  (testing, deployment, release notes, design systems, …).
- The user says "find a skill for X" / "is there a skill that does X".
- A task would clearly benefit from a specialized capability this project
  doesn't have yet (check the project's existing skills first).

## 2. Search

1. Browse the leaderboard at https://skills.sh/ for popular, battle-tested
   options first (install counts are the strongest quality signal).
2. Or search from the terminal:

   ```bash
   npx skills find <query>          # keyword search
   npx skills find <query> --owner vercel-labs   # scope to an org
   ```

3. Rank what you find:
   - install counts (prefer 1k+),
   - source reputation (vercel-labs, anthropics, microsoft, established orgs),
   - GitHub stars and recent activity.

## 3. Present candidates

Show the user the top 2-3 options with: name, one-line purpose, install
count, source org, and the repo link. Recommend one and say why.

## 4. Install — through AgentDesk ONLY

**Never run `npx skills add`** — direct installs bypass the project's skill
registry, the admin review gate, and team-wide skill sync, so the team ends
up with unmanaged skills. Instead:

1. Propose the chosen skill for this project: AgentDesk → **Skills →
   External Skills → Import**, with the repo URL (an admin can also do this
   via `POST /skill-discovery/discover/import`).
2. An admin reviews the pending entry (security gate), installs the vendored
   snapshot, and enables it for the project.
3. The skill then syncs to every developer's CLI through the normal
   AgentDesk skill sync — same as built-in skills.

Tell the user which admin action is pending after you propose the import.

## 5. Nothing found?

Offer to do the task directly with your general capabilities, or suggest
creating a project skill for it (a completed use case can be promoted to a
skill from the use case view).

---
_Adapted for AgentDesk from [vercel-labs/skills `find-skills`](https://github.com/vercel-labs/skills/blob/main/skills/find-skills/SKILL.md) (MIT). Changed: installation is handed off to AgentDesk's External Skills review flow instead of `npx skills add -g -y`._
