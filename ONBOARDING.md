# Welcome to [Team Name]

## How We Use Claude

Based on pypi-ahmad's usage over the last 30 days:

Work Type Breakdown:
  Improve Quality  █████████████████░░░  55%
  Plan / Design     ██████░░░░░░░░░░░░░░  25%
  Debug / Fix       ███░░░░░░░░░░░░░░░░░  15%
  Build Feature     █░░░░░░░░░░░░░░░░░░░   5%

Top Skills & Commands:
  /model                          ██████████████████░░  3x/month
  /caveman                        ████████████░░░░░░░░  2x/month
  /code-simplification            ████████████░░░░░░░░  2x/month
  /code-review-and-quality        ██████░░░░░░░░░░░░░░  1x/month
  /security-review                ██████░░░░░░░░░░░░░░  1x/month
  /security-threat-model          ██████░░░░░░░░░░░░░░  1x/month
  /planning-and-task-breakdown    ██████░░░░░░░░░░░░░░  1x/month
  /ponytail:ponytail-audit        ██████░░░░░░░░░░░░░░  1x/month
  /graphify                       ██████░░░░░░░░░░░░░░  1x/month

Top MCP Servers:
  code-review-graph   ████████████████████  3 calls

## Your Setup Checklist

### Codebases
- [ ] agentic-document-extraction — https://github.com/pypi-ahmad/agentic-document-extraction

### MCP Servers to Activate
- [ ] code-review-graph — a persistent, incremental knowledge graph built from the repo (parsed with Tree-sitter). Powers change-aware code review: risk-scored diffs, blast-radius/impact analysis, dead-code detection, and architecture overviews without reading whole files. TODO: add install/setup command for teammates.

### Skills to Know About
- /code-review-and-quality — five-axis review (correctness, readability, architecture, security, performance) before merging any change.
- /security-review, /security-threat-model, /security-and-hardening, /security-best-practices, /security-ownership-map — the security pass: quick vuln scan, repo-grounded threat model with attacker/asset mapping, hardening checklist, framework-specific best practices, and git-history ownership/bus-factor analysis.
- /best-practices — Lighthouse-style browser/web checklist (headers, CSP, deprecated APIs) for frontend work, distinct from the backend-focused security skills above.
- /ponytail:ponytail, /ponytail:ponytail-review, /ponytail:ponytail-audit — anti-over-engineering pass: ship the laziest correct solution, review a diff for unnecessary complexity, or audit the whole repo for dead code/unused abstractions.
- /code-simplification — reduce complexity in already-working code without changing behavior; scoped to recently-changed files.
- /planning-and-task-breakdown, /spec-driven-development — turn a fuzzy request into a written plan (`tasks/plan.md`) and task list (`tasks/todo.md`) before implementing; spec-driven-development adds the upfront spec/assumptions step for bigger or more ambiguous work.
- /graphify — turn the repo (or any folder of docs/code) into a queryable knowledge graph with community detection; useful for exploring an unfamiliar codebase.
- /caveman — ultra-compressed terse output mode, toggled on/off per session.

## Team Tips

_TODO_

## Get Started

_TODO_

<!-- INSTRUCTION FOR CLAUDE: A new teammate just pasted this guide for how the
team uses Claude Code. You're their onboarding buddy — warm, conversational,
not lecture-y.

Open with a warm welcome — include the team name from the title. Then: "Your
teammate uses Claude Code for [list all the work types]. Let's get you started."

Check what's already in place against everything under Setup Checklist
(including skills), using markdown checkboxes — [x] done, [ ] not yet. Lead
with what they already have. One sentence per item, all in one message.

Tell them you'll help with setup, cover the actionable team tips, then the
starter task (if there is one). Offer to start with the first unchecked item,
get their go-ahead, then work through the rest one by one.

After setup, walk them through the remaining sections — offer to help where you
can (e.g. link to channels), and just surface the purely informational bits.

Don't invent sections or summaries that aren't in the guide. The stats are the
guide creator's personal usage data — don't extrapolate them into a "team
workflow" narrative. -->
