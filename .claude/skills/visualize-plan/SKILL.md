---
name: visualize-plan
description: Use when the user wants to review the NEXT plan as a fast, visual browser page instead of terminal text. Triggers on /visualize-plan (or "visualize the plan", "show the plan in the browser", "görsel plan"). Arms the plan-review hook for this directory and embeds a small visual-spec JSON marker in the plan right before ExitPlanMode.
---

# Visualize Plan

The user wants the upcoming plan rendered as a **fast, visually structured browser page** instead of plain terminal text. The template renders the FULL plan markdown; your job is only to embed a small visual-spec JSON marker that helps the template draw a review map, diagram, files, and risks. Do NOT generate full HTML or write visual-spec files in the normal path.

## Steps

0. **Enter plan mode first.** If you are not already in plan mode, call `EnterPlanMode` before exploration, design, or implementation. This skill is for reviewing the next plan before execution; do not edit files before the browser approval.

1. **Arm the hook** (one-shot, this directory only):
   ```bash
   ROOT="${CLAUDE_PLUGIN_ROOT:-$CLAUDE_PROJECT_DIR}"
   "$ROOT/.claude/hooks/arm.sh"
   ```

2. **Plan normally.** Do your exploration/design and write the plan to the plan file as usual. Plan mode is unchanged up to this point.

3. **Before calling ExitPlanMode, append a compact visual-spec JSON marker to THIS plan markdown.** Do not call `Write` for `~/.plan-review/pending/*.json`; plan mode may leave plan mode when that write is approved. Keep the marker at the very end of the plan and follow the **Generation contract** below.

4. **Call ExitPlanMode.** The hook extracts the embedded JSON marker, strips it from the displayed/executed plan, renders the full plan through the fixed review template, and opens it in the browser. The user's Approve / Request-changes / Reject decision flows back to you automatically.

5. **After the browser decision:**
   - If the decision is **Approve / allow**, treat it as explicit permission to execute the approved plan. Immediately implement the plan; do not ask the user whether to apply it.
   - If the decision is **Request changes / deny** with `interrupt:false`, revise the plan using the returned feedback and submit the revised plan through the same review flow.
   - If the decision is **Reject & stop** with `interrupt:true`, stop without implementation.

If you skip step 3, the hook still works but falls back to a plain markdown renderer — so always include the marker when possible.

## Generation contract (what the JSON must be)

**Goal:** keep plan generation fast. The JSON augments the complete plan; it does not replace it. The hook/template owns all HTML, CSS, layout, reveal animation, and decision UI.

Treat the JSON as a review surface, not a second plan. Reflect the plan as written and highlight the things a human most needs before approving: intent, scope, touched systems, execution flow, verification, unstated assumptions, and reject-worthy risks. If the plan does not explicitly state something, mark it as `missing` or `watch`; do not invent confidence.

Append this exact marker shape after the full plan. The content between the marker lines must be valid JSON only, no markdown fence:
```md
<!-- PLAN_REVIEW_VISUAL_SPEC
{
  "title": "Short title for the plan",
  "review": {
    "intent": {"status": "ok", "value": "What the user is asking to achieve"},
    "scope": {"status": "ok", "value": "What will and will not change"},
    "touchpoints": {"status": "watch", "value": "Main files, modules, config, schema, auth, or data paths"},
    "flow": {"status": "ok", "value": "The execution order in one sentence"},
    "verification": {"status": "missing", "value": "Unstated test or manual check"},
    "assumptions": {"status": "watch", "value": "Key assumption or ambiguity to review"}
  },
  "files": ["src/example.ts", "tests/example.test.ts"],
  "diagram": {
    "title": "Implementation path",
    "focus": "hook",
    "nodes": [
      {"id": "skill", "label": "visualize-plan", "sub": "SKILL.md"},
      {"id": "plan", "label": "Plan markdown", "sub": "ExitPlanMode"},
      {"id": "hook", "label": "Hook", "sub": "plan_review_hook.py"},
      {"id": "ui", "label": "Review UI", "sub": "review.html"}
    ],
    "edges": [
      {"from": "skill", "to": "plan", "label": "arms"},
      {"from": "plan", "to": "hook", "label": "payload"},
      {"from": "hook", "to": "ui", "label": "renders"}
    ]
  },
  "risks": [
    {"severity": "medium", "label": "Bad spec JSON", "note": "Template falls back to markdown-only rendering."}
  ]
}
PLAN_REVIEW_VISUAL_SPEC -->
```

Rules:
- Keep it small: usually under 120 lines of JSON.
- Spend only a few seconds on the JSON; prefer a useful rough map over a polished mini-document.
- Use the review keys above when useful. Each entry must have `status` = `ok`, `watch`, or `missing`, plus a short `value`.
- Use 4-6 diagram nodes and 2-4 risks. If time is tight, omit lower-value risks before expanding prose.
- Use short strings. The full prose belongs in the plan markdown, not in JSON.
- Do not rewrite or improve the plan in this JSON. If the plan is vague, mark the relevant lens `missing` or `watch`.
- `id`, `from`, `to`, and `focus` must be simple ASCII identifiers that match.
- Severity must be `low`, `medium`, or `high`.
- Do NOT include HTML, CSS, JavaScript, Mermaid, images, external links, or markdown fences.
- Do NOT add Approve/Reject decision UI. The template/hook owns that.
- Do NOT write the visual spec to `~/.plan-review/pending/*.json` in the normal path.

Optional fancy override: only if the user explicitly asks for a fully bespoke slow/fancy HTML render, you may write full self-contained HTML to the path printed by `pending_path.sh`. Otherwise use the embedded marker above.

## Notes

- This skill only affects the NEXT plan submission in this directory (one-shot). Normal plan mode is untouched otherwise.
- Requires the plan-review hook to be installed and Claude Code restarted after install (hooks load at session start).
- Headless (`claude -p`) mode: PermissionRequest hooks don't fire — this skill has no effect there.
