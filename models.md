# Models

Which Claude model for which job, and how to switch. Defaults are fine most of the time — this is for when they aren't.

## The tiers

| Model | Best for | Why |
|-------|----------|-----|
| **Opus** | Planning, architecture, hard debugging, reviews | Strongest reasoning; worth the cost when a wrong call is expensive |
| **Sonnet** | Daily build driver — most implementation | The sweet spot of capable + fast for writing code against a clear plan |
| **Haiku** | Fast/cheap parallel work, simple edits, bulk grunt tasks | Cheapest and fastest; good when the task is mechanical |

Rule of thumb: **think with Opus, build with Sonnet, sweep with Haiku.** Plan a feature in Opus (where a bad architectural call is costly), hand the approved plan to Sonnet to implement, and let Haiku handle repetitive low-judgment passes.

## Switching

- In a session: `/model` to pick a tier.
- Pin a model for a reproducible session via CLI flag or `settings.json` (see the official Claude Code docs for the exact keys — they change, so I check rather than memorize).
- Some setups allow per-subagent model overrides, so a cheap model handles fan-out work while the main session stays on a stronger one.

## Watching usage

- `/usage` — my plan limits / billing. Shows the rolling usage window and weekly limits (or a session dollar estimate on an API key).
- `/context` — how full **this session's context window** is. Different question entirely: it tells me when a session is getting bloated and answer quality may degrade.

When `/context` is getting full and the task has drifted, the fix is usually a fresh session, not a bigger model.

## A note on training cutoffs

A model only knows what it was trained on (plus what it can look up). For a fast-moving framework, it may not know the latest release exists unless I tell it — which is exactly why Boost and up-to-date guideline files matter: they hand the agent current, project-specific truth instead of relying on stale training data.
