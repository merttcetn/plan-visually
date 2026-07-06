# plan-visually

**Opt-in browser review for Claude Code plans.** When armed, `plan-visually` renders the
plan Claude is about to execute as a warm, self-contained HTML page in your browser — with
a review map, a node-graph diagram, touched files, and risks alongside the full plan text —
and waits there for your **Approve / Request changes / Reject** decision.

Default plan mode is **untouched** unless you explicitly arm it.

<!-- TODO: add a screenshot or GIF of the review page here, e.g. ![Review page](docs/review.png) -->
<!-- No demo asset ships yet — replace this comment with the image once captured. -->

## What it does

`plan-visually` registers a `PermissionRequest` hook on `ExitPlanMode`. On its own the hook
stays dormant and passes through to Claude Code's normal terminal approval.

When you run `/visualize-plan`, the skill arms a **one-shot** trigger for the current
directory and embeds a small visual-spec JSON marker at the end of the plan. On the next
`ExitPlanMode`, the hook:

1. extracts and strips that marker (so the executed plan stays clean),
2. renders the **complete** plan markdown through a fixed template, using the JSON to draw
   the review lens (intent, scope, touchpoints, flow, verification, assumptions), a node
   diagram, the file list, and risks,
3. opens the page in your browser on a local `127.0.0.1` server, and
4. returns your decision to Claude.

**Approve = permission to execute.** After you approve in the browser, Claude implements the
approved plan immediately — there is no second "apply this plan?" prompt. **Request changes**
sends your feedback back to Claude for a revision. **Reject & stop** halts without implementing.

## Key properties

- **Opt-in and dormant by default.** Not armed → the hook exits silently and normal plan
  mode behaves exactly as before.
- **No dependencies, no build.** Python 3 **standard library only** — no pip, no build step.
- **Self-contained visuals.** Every diagram is hand-authored HTML + CSS + inline SVG. No
  CDNs, no web fonts, no Mermaid, no external libraries.
- **Full plan, not a summary.** The page contains the entire plan the executing agent needs;
  the diagrams sit alongside the prose, they don't replace it.
- **Fail-safe.** On any error the hook exits cleanly and falls back to the normal terminal
  approval, so it can never block your workflow.

## Install

Install through the Claude Code plugin marketplace:

```text
/plugin marketplace add merttcetn/plan-visually
/plugin install plan-visually
```

> **Restart Claude Code (or run `/reload-plugins`) after installing.** Hooks are loaded at
> session start, so a freshly installed hook only takes effect in a new session.

## Usage

1. Run `/visualize-plan` (also triggers on "visualize the plan", "show the plan in the
   browser", or "görsel plan").
2. Give Claude a planning task as usual. Claude plans normally, then embeds the visual-spec
   marker before exiting plan mode.
3. The review page opens in your browser. Choose **Approve**, **Request changes** (type
   feedback first — it's sent immediately), or **Reject & stop**.

The trigger is one-shot and scoped to the current directory: it only affects the **next**
plan submission there. Everything else stays on the standard flow.

## Requirements

- `python3` on your `PATH`.
- **macOS / Linux.** The arm/path helper scripts use `shasum`. On **Windows** run them under
  a POSIX shell (Git Bash or WSL); a bare Windows shell is not supported.
- **Not available in headless mode.** `claude -p` does not fire `PermissionRequest` hooks, so
  this plugin has no effect there.

## License

[MIT](LICENSE) © 2026 Mert Cetin

---

### Maintainer note: set the GitHub "About"

The repo description and topics still need to be set (they can't be configured from the
plugin itself). Either:

- **Web:** repo page → the **About** gear → add a description and topics; or
- **CLI** (requires the [GitHub CLI](https://cli.github.com/)):

  ```bash
  gh repo edit merttcetn/plan-visually \
    --description "Opt-in browser review for Claude Code plans (ExitPlanMode hook + /visualize-plan skill)." \
    --add-topic claude-code --add-topic plugin --add-topic hooks \
    --add-topic planning --add-topic developer-tools
  ```
