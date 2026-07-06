import hashlib
import importlib.util
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HOOK_PATH = ROOT / ".claude" / "hooks" / "plan_review_hook.py"


def load_hook():
    spec = importlib.util.spec_from_file_location("plan_review_hook", HOOK_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class PlanReviewHookTests(unittest.TestCase):
    def setUp(self):
        self.hook = load_hook()
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.hook.PENDING_DIR = self.tmp.name

    def pending_file(self, cwd, suffix):
        return Path(self.tmp.name) / (self.hook.trigger_key(cwd) + suffix)

    def test_load_ai_page_reads_and_consumes_pending_html(self):
        path = self.pending_file("/proj/x", ".html")
        path.write_text("<html><body>Fancy</body></html>", encoding="utf-8")

        self.assertEqual(self.hook.load_ai_page("/proj/x"), "<html><body>Fancy</body></html>")
        self.assertFalse(path.exists())

    def test_load_ai_page_returns_none_when_missing(self):
        self.assertIsNone(self.hook.load_ai_page("/proj/x"))

    def test_load_visual_spec_reads_and_consumes_pending_json(self):
        path = self.pending_file("/proj/x", ".json")
        path.write_text(json.dumps({"title": "Hybrid"}), encoding="utf-8")

        self.assertEqual(self.hook.load_visual_spec("/proj/x"), {"title": "Hybrid"})
        self.assertFalse(path.exists())

    def test_load_visual_spec_consumes_malformed_pending_json(self):
        path = self.pending_file("/proj/x", ".json")
        path.write_text('{"broken": ', encoding="utf-8")

        self.assertEqual(self.hook.load_visual_spec("/proj/x"), {})
        self.assertFalse(path.exists())

    def test_extract_embedded_visual_spec_strips_marker(self):
        plan = """# Plan

Do the work.

<!-- PLAN_REVIEW_VISUAL_SPEC
{"title":"Embedded","review":{"intent":{"status":"ok","value":"Do the work"}}}
PLAN_REVIEW_VISUAL_SPEC -->
"""

        clean, spec = self.hook.extract_embedded_visual_spec(plan)

        self.assertEqual(spec["title"], "Embedded")
        self.assertNotIn("PLAN_REVIEW_VISUAL_SPEC", clean)
        self.assertEqual(clean, "# Plan\n\nDo the work.")

    def test_extract_embedded_visual_spec_strips_malformed_marker(self):
        plan = """# Plan

<!-- PLAN_REVIEW_VISUAL_SPEC
{"broken":
PLAN_REVIEW_VISUAL_SPEC -->
"""

        clean, spec = self.hook.extract_embedded_visual_spec(plan)

        self.assertEqual(spec, {})
        self.assertNotIn("PLAN_REVIEW_VISUAL_SPEC", clean)
        self.assertEqual(clean, "# Plan")

    def test_build_static_page_escapes_inline_script_json(self):
        plan = "before </script><div id=\"breakout\">broken</div> ç"
        page = self.hook.build_static_page(
            plan,
            "/proj/x",
            "session",
            {"title": "</script><main>bad</main>"},
        )

        self.assertIn("\\u003c/script\\u003e", page)
        self.assertIn("\\u003cdiv id=", page)
        self.assertIn("ç", page)
        self.assertNotIn('<div id="breakout">', page)
        self.assertNotIn("<main>bad</main>", page)

    def test_path_helpers_match_hook_key(self):
        expected = hashlib.sha1(b"/proj/x").hexdigest()[:16]
        env = os.environ.copy()
        env["HOME"] = self.tmp.name

        html = subprocess.run(
            [str(ROOT / ".claude" / "hooks" / "pending_path.sh"), "/proj/x"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        ).stdout.strip()
        visual = subprocess.run(
            [str(ROOT / ".claude" / "hooks" / "visual_spec_path.sh"), "/proj/x"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        ).stdout.strip()

        self.assertEqual(Path(html).name, expected + ".html")
        self.assertEqual(Path(visual).name, expected + ".json")

    def test_arm_clears_stale_pending_files_for_cwd(self):
        expected = hashlib.sha1(b"/proj/x").hexdigest()[:16]
        pending = Path(self.tmp.name) / ".plan-review" / "pending"
        pending.mkdir(parents=True)
        (pending / (expected + ".json")).write_text("stale", encoding="utf-8")
        (pending / (expected + ".html")).write_text("stale", encoding="utf-8")
        env = os.environ.copy()
        env["HOME"] = self.tmp.name

        subprocess.run(
            [str(ROOT / ".claude" / "hooks" / "arm.sh"), "/proj/x"],
            check=True,
            env=env,
            capture_output=True,
            text=True,
        )

        self.assertFalse((pending / (expected + ".json")).exists())
        self.assertFalse((pending / (expected + ".html")).exists())
        self.assertTrue((Path(self.tmp.name) / ".plan-review" / "triggers" / expected).exists())

    def test_skill_copies_are_in_sync(self):
        local = ROOT / ".claude" / "skills" / "visualize-plan" / "SKILL.md"
        plugin = ROOT / "skills" / "visualize-plan" / "SKILL.md"

        self.assertEqual(local.read_text(encoding="utf-8"), plugin.read_text(encoding="utf-8"))

    def test_skill_treats_browser_approval_as_execute_permission(self):
        skill = (ROOT / ".claude" / "skills" / "visualize-plan" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("Immediately implement the plan", skill)
        self.assertIn("do not ask the user whether to apply it", skill)

    def test_skill_uses_embedded_visual_spec_marker_not_pending_json(self):
        skill = (ROOT / ".claude" / "skills" / "visualize-plan" / "SKILL.md").read_text(encoding="utf-8")

        self.assertIn("PLAN_REVIEW_VISUAL_SPEC", skill)
        self.assertIn("Do not call `Write` for `~/.plan-review/pending/*.json`", skill)
        self.assertNotIn("visual_spec_path.sh", skill)

    def test_review_template_supports_review_lenses(self):
        template = (ROOT / ".claude" / "hooks" / "review.html").read_text(encoding="utf-8")

        self.assertIn("spec.review", template)
        self.assertIn("intent:'Intent'", template)
        self.assertIn("verification:'Verification'", template)
        self.assertIn("summary-status", template)

    def test_review_template_supports_common_markdown_blocks(self):
        template = (ROOT / ".claude" / "hooks" / "review.html").read_text(encoding="utf-8")

        self.assertIn("function isTableSeparator", template)
        self.assertIn("function renderTable", template)
        self.assertIn("html+='<hr>'", template)
        self.assertIn(".md table", template)

    def test_empty_reject_asks_claude_for_follow_up(self):
        template = (ROOT / ".claude" / "hooks" / "review.html").read_text(encoding="utf-8")
        hook = (ROOT / ".claude" / "hooks" / "plan_review_hook.py").read_text(encoding="utf-8")
        expected = "Ask one concise follow-up question"

        self.assertIn(expected, template)
        self.assertIn(expected, hook)
        decision = self.hook.to_decision({"action": "reject"})
        self.assertEqual(
            decision["hookSpecificOutput"]["decision"]["message"],
            self.hook.DEFAULT_REJECT_FEEDBACK,
        )
        self.assertFalse(decision["hookSpecificOutput"]["decision"]["interrupt"])

    def test_request_changes_is_single_click(self):
        template = (ROOT / ".claude" / "hooks" / "review.html").read_text(encoding="utf-8")
        hook = (ROOT / ".claude" / "hooks" / "plan_review_hook.py").read_text(encoding="utf-8")

        self.assertIn("rej.onclick=()=>send('reject')", template)
        self.assertIn("rej.onclick=function(){ send('reject'); }", hook)
        self.assertNotIn("Send to Claude", template)
        self.assertNotIn("Send to Claude", hook)

    def test_approve_can_return_clean_updated_input(self):
        decision = self.hook.to_decision(
            {"action": "approve"},
            {"plan": "# Plan\n\nClean", "allowedPrompts": []},
        )

        self.assertEqual(decision["hookSpecificOutput"]["decision"]["behavior"], "allow")
        self.assertEqual(
            decision["hookSpecificOutput"]["decision"]["updatedInput"]["plan"],
            "# Plan\n\nClean",
        )


if __name__ == "__main__":
    unittest.main()
