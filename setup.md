# Setup

What to install before working, and how to wire Claude Code into a project.

## Checklist

- [ ] Install Claude Code
- [ ] Log in
- [ ] (Laravel projects) Install Laravel Boost
- [ ] (Optional) Install the `feature-dev` plugin
- [ ] Read [the workflow](README.md#the-workflow) before the first real task

---

## 1 — Install Claude Code

Follow the official instructions at [docs.claude.com/en/docs/claude-code](https://docs.claude.com/en/docs/claude-code). Confirm with `claude --version`.

**Keeping work and personal accounts separate.** Each account gets its own config dir (`CLAUDE_CONFIG_DIR`), so skills, settings, history, and login stay completely isolated. The account a session uses is decided by **which command I launch**, not which folder I'm in.

My actual setup:

| Command | Config dir | Account | Use for |
|---------|-----------|---------|---------|
| `claude` (default) | `~/.claude` | **personal** | personal projects |
| `claude-simply` | `~/.claude-simply` | **work** | the work repo only |

The work alias lives in `~/.zshrc`:

```bash
alias claude-simply='CLAUDE_CONFIG_DIR="$HOME/.claude-simply" claude'
```

Default `claude` is already my personal account, so personal work just uses `claude` — no extra alias needed. The rule: **`claude` for personal, `claude-simply` for work.** That keeps personal code and conversations out of the work workspace entirely (a work admin can't see the personal account).

> Tip: this pairs with per-repo git identity. The global git identity may be a work address, so set a repo-local `git config user.name` / `user.email` on personal repos so commits go out under the right name regardless.

---

## 2 — Log in

Open Claude Code; it should prompt for credentials, or run `/login`. Pick a terminal theme (personal preference). Authenticate through the browser and paste the code back into the CLI.

---

## 3 — Laravel Boost (Laravel projects only)

Boost is the most valuable piece of tooling for a Laravel project: it gives the agent the project's *real* routes, models, and migrations over MCP, instead of letting it guess. That cuts hallucinations and saves the tokens the agent would otherwise spend rediscovering the codebase.

> ⚠️ Boost supports Laravel **12 and 13**. On older releases, use Claude Code without it — Boost can otherwise generate code for the wrong framework version.

From the Laravel app directory (where `artisan` lives):

```bash
composer require laravel/boost --dev
php artisan boost:install
```

`boost:install` generates the MCP config, AI guideline files (`CLAUDE.md` / `AGENTS.md`), and a `boost.json`. To run it non-interactively:

```bash
php artisan boost:install --guidelines --skills --mcp --no-interaction
```

It usually registers the MCP server automatically. If not:

```bash
claude mcp add -s local -t stdio laravel-boost php artisan boost:mcp
```

A project-scoped MCP server (written to `.mcp.json`) needs a **one-time approval** the next time I launch `claude` in that directory. Confirm it's connected with `claude mcp list` — `laravel-boost` should show as connected (not "pending approval").

### Boost files: commit or ignore?

For a **personal project**, commit them — `CLAUDE.md`, `AGENTS.md`, `.mcp.json`, `boost.json` — so the agent context travels with the repo. (`boost:install` can regenerate them, so ignoring them is also valid; it's a preference.) If a project ends up with two `CLAUDE.md` files (e.g. a root one and a framework one in a subdir), reconcile them so guidance isn't split and duplicated.

---

## 4 — feature-dev plugin (optional)

Gives a `/feature-dev:feature-dev` flow for scoped features plus a `code-review` skill. Install from the plugin marketplace inside a session:

```text
/plugin marketplace add <marketplace-url>
/plugin install feature-dev
```

Restart Claude Code after installing; plugins and skills are read at session start. If a slash command says "unknown," confirm with `claude plugins list`.

---

## Troubleshooting

- **A skill didn't auto-trigger.** Auto-trigger is pattern-matched and not guaranteed. Invoke it by name: *"Use the security-review skill on this diff."*
- **Boost MCP won't connect.** Re-run the `claude mcp add` line from the project root. Check `php artisan boost:mcp` runs standalone (it should produce stdio output and hang until interrupted). If artisan itself errors, Boost can't connect.
- **Boost says my Laravel version is unsupported.** Use Claude without Boost on that project until it's supported.
- **Commits show the wrong name.** Set a repo-local `git config user.name` / `user.email`; it overrides the global for that repo only.
