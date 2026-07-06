#!/usr/bin/env python3
"""
Plan Review Hook — hybrid plan visualization.

PermissionRequest hook (matcher: ExitPlanMode). Stays DORMANT unless manually
armed via the /visualize-plan skill (arm.sh). When armed, it opens the plan in
the browser for review and blocks until the user decides.

Render paths:
  1. Hybrid    : Claude embeds a small visual spec JSON in a hidden
                 PLAN_REVIEW_VISUAL_SPEC plan comment; the hook strips it,
                 renders the clean plan with review.html, and lets the
                 template draw visuals.
  2. AI page   : if Claude wrote a bespoke visualization to
                 ~/.plan-review/pending/<cwd-key>.html, serve THAT. This is kept
                 as an optional/fancy override.
  3. Legacy    : if a pending <cwd-key>.json exists, consume it as a fallback.
  4. Fallback  : otherwise render the plan markdown with review.html.

Decisions (verified live — see FINDINGS.md):
  approve         -> {"behavior":"allow"}
  request changes -> {"behavior":"deny","message":<feedback>,"interrupt":false}
  reject & stop   -> {"behavior":"deny","message":<feedback>,"interrupt":true}

SAFETY: on ANY failure, exit 0 with NO output -> Claude Code falls back to its
normal terminal approval prompt instead of breaking the session.
"""
import sys, os, json, threading, webbrowser, hashlib, re
from http.server import BaseHTTPRequestHandler, HTTPServer

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "review.html")
STATE_DIR = os.path.expanduser("~/.plan-review")
TRIGGER_DIR = os.path.join(STATE_DIR, "triggers")
PENDING_DIR = os.path.join(STATE_DIR, "pending")
VISUAL_SPEC_RE = re.compile(
    r"\n?<!--\s*PLAN_REVIEW_VISUAL_SPEC\s*(.*?)\s*PLAN_REVIEW_VISUAL_SPEC\s*-->\s*",
    re.DOTALL,
)
DEFAULT_REJECT_FEEDBACK = (
    "The user requested changes in the browser review but did not provide written feedback. "
    "Ask one concise follow-up question about what should change before revising the plan."
)
DEFAULT_STOP_FEEDBACK = "The user rejected the plan and stopped execution from the browser review."


def trigger_key(cwd: str) -> str:
    return hashlib.sha1((cwd or "").encode("utf-8")).hexdigest()[:16]


def is_armed_and_consume(cwd: str) -> bool:
    """One-shot manual trigger; keeps DEFAULT plan mode untouched."""
    if os.environ.get("PLAN_REVIEW_FORCE") == "1":
        return True
    path = os.path.join(TRIGGER_DIR, trigger_key(cwd))
    if not os.path.exists(path):
        return False
    try:
        os.remove(path)
    except Exception:
        pass
    return True


# Injected into every AI-authored page: the decision bar only.
# All ids/classes are `pr-` prefixed and heavily scoped so they never collide
# with whatever the AI generated.
INJECT = r"""
<style>
  body{padding-bottom:172px !important;}
  #pr-bar{position:fixed;left:0;right:0;bottom:0;z-index:2147483000;
    background:rgba(250,249,245,.94);backdrop-filter:blur(12px);
    border-top:1.5px solid #D1CFC5;box-shadow:0 -12px 32px -24px rgba(20,20,19,.55);
    padding:15px 24px 17px;font:14px/1.4 system-ui,-apple-system,"Segoe UI",Roboto,sans-serif;color:#3D3D3A;}
  #pr-inner{max-width:1120px;margin:0 auto;}
  #pr-fb{max-height:240px;overflow:hidden;opacity:1;margin-bottom:14px;transition:opacity .2s ease;}
  #pr-fb .lbl{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.09em;text-transform:uppercase;color:#87867F;margin-bottom:7px;}
  #pr-fb textarea{width:100%;min-height:78px;resize:vertical;background:#fff;color:#141413;
    border:1.5px solid #D1CFC5;border-radius:10px;padding:12px 14px;font:14.5px/1.55 system-ui,-apple-system,sans-serif;}
  #pr-fb textarea:focus{outline:none;border-color:#D97757;box-shadow:0 0 0 3px rgba(217,119,87,.14);}
  #pr-row{display:flex;align-items:center;gap:10px 14px;flex-wrap:wrap;}
  #pr-eyebrow{font-family:ui-monospace,Menlo,monospace;font-size:11px;letter-spacing:.14em;text-transform:uppercase;color:#87867F;white-space:nowrap;margin-right:auto;}
  #pr-actions{display:flex;align-items:center;gap:10px;flex-wrap:wrap;}
  #pr-bar button{font:600 14px/1 system-ui,-apple-system,sans-serif;border-radius:9px;cursor:pointer;
    border:1.5px solid transparent;padding:12px 20px;transition:filter .15s,border-color .15s,color .15s,background .15s,box-shadow .15s;}
  #pr-approve{background:#D97757;color:#fff;box-shadow:0 1px 0 rgba(20,20,19,.05);}
  #pr-approve:hover{filter:brightness(1.06);box-shadow:0 5px 16px -7px rgba(217,119,87,.75);}
  #pr-reject{background:#fff;color:#3D3D3A;border-color:#D1CFC5;}
  #pr-reject:hover{border-color:#D97757;color:#141413;}
  #pr-reject.send{background:#D97757;color:#fff;border-color:transparent;box-shadow:0 1px 0 rgba(20,20,19,.05);}
  #pr-reject.send:hover{filter:brightness(1.06);}
  #pr-stop{background:transparent;color:#87867F;border:none;padding:12px 4px;
    text-decoration:underline;text-underline-offset:3px;text-decoration-color:#D1CFC5;}
  #pr-stop:hover{color:#8A3B1E;text-decoration-color:#D97757;}
  #pr-done{display:none;text-align:center;color:#87867F;padding:5px 0;}
  #pr-done b{color:#141413;}
  @media (prefers-reduced-motion:reduce){#pr-fb{transition:none;}}
  @media (max-width:640px){#pr-eyebrow{display:none;}#pr-actions{margin-left:0;width:100%;}#pr-approve{flex:1;}}
</style>
<div id="pr-bar"><div id="pr-inner">
  <div id="pr-fb"><div class="lbl">Feedback &rarr; Claude</div>
    <textarea id="pr-feedback" placeholder="Optional: describe what to change. Leave empty to make Claude ask you what should improve."></textarea></div>
  <div id="pr-row">
    <span id="pr-eyebrow">Your decision</span>
    <div id="pr-actions">
      <button id="pr-approve">Approve &amp; execute</button>
      <button id="pr-reject">Request changes</button>
      <button id="pr-stop" title="Stop Claude entirely">Reject &amp; stop</button>
    </div>
  </div>
  <div id="pr-done">Decision sent &middot; <b>you can close this tab.</b></div>
</div></div>
<script>
  (function(){
    var DEFAULT_REJECT_FEEDBACK='The user requested changes in the browser review but did not provide written feedback. Ask one concise follow-up question about what should change before revising the plan.';
    var DEFAULT_STOP_FEEDBACK='The user rejected the plan and stopped execution from the browser review.';
    var sent=false, fb=document.getElementById('pr-fb'), rej=document.getElementById('pr-reject');
    function fin(){ document.getElementById('pr-row').style.display='none'; fb.style.display='none';
      try{ window.open('','_self'); window.close(); }catch(e){}
      setTimeout(function(){ document.getElementById('pr-done').style.display='block'; },150); }
    async function send(a){ if(sent)return; sent=true;
      var raw=(document.getElementById('pr-feedback').value||'');
      var feedback=raw.trim()?raw:(a==='reject'?DEFAULT_REJECT_FEEDBACK:(a==='reject_stop'?DEFAULT_STOP_FEEDBACK:''));
      try{ await fetch('/decision',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({action:a, feedback:feedback})}); }catch(e){}
      fin(); }
    document.getElementById('pr-approve').onclick=function(){ send('approve'); };
    rej.onclick=function(){ send('reject'); };
    document.getElementById('pr-stop').onclick=function(){
      send('reject_stop'); };
  })();
</script>
"""


def inject_controls(html: str) -> str:
    """Insert the decision bar before </body> (or append)."""
    lower = html.lower()
    idx = lower.rfind("</body>")
    if idx == -1:
        return html + INJECT
    return html[:idx] + INJECT + html[idx:]


def js_json(value) -> str:
    """JSON safe to embed inside an inline <script> block."""
    return (json.dumps(value, ensure_ascii=False)
            .replace("&", "\\u0026")
            .replace("<", "\\u003c")
            .replace(">", "\\u003e")
            .replace("\u2028", "\\u2028")
            .replace("\u2029", "\\u2029"))


def build_static_page(plan: str, cwd: str, session: str, visual_spec=None) -> str:
    with open(TEMPLATE, "r", encoding="utf-8") as f:
        html = f.read()
    return (html
            .replace("__PLAN_JSON__", js_json(plan))
            .replace("__CWD_JSON__", js_json(cwd))
            .replace("__SESSION_JSON__", js_json(session))
            .replace("__VISUAL_SPEC_JSON__", js_json(visual_spec or {})))


def extract_embedded_visual_spec(plan: str):
    """Return (plan_without_marker, visual_spec) from an embedded comment block."""
    visual_spec = {}
    for match in VISUAL_SPEC_RE.finditer(plan or ""):
        if visual_spec:
            continue
        try:
            parsed = json.loads(match.group(1).strip())
            if isinstance(parsed, dict):
                visual_spec = parsed
        except Exception:
            pass
    clean_plan = VISUAL_SPEC_RE.sub("\n", plan or "").strip()
    return clean_plan, visual_spec


def load_ai_page(cwd: str):
    """Return the AI-authored HTML for this cwd (consumed), or None."""
    path = os.path.join(PENDING_DIR, trigger_key(cwd) + ".html")
    if not os.path.exists(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            html = f.read()
        os.remove(path)  # consume
        return html
    except Exception:
        return None


def load_visual_spec(cwd: str):
    """Return the legacy pending visual spec JSON for this cwd (consumed), or {}."""
    path = os.path.join(PENDING_DIR, trigger_key(cwd) + ".json")
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            spec = json.load(f)
        try:
            os.remove(path)  # consume
        except Exception:
            pass
        if isinstance(spec, dict):
            return spec
    except Exception:
        pass
    try:
        os.remove(path)  # consume even malformed stale JSON
    except Exception:
        pass
    return {}


def to_decision(obj: dict, approve_updated_input=None):
    action = (obj or {}).get("action")
    if action == "approve":
        decision = {"behavior": "allow"}
        if approve_updated_input:
            decision["updatedInput"] = approve_updated_input
    elif action == "reject":
        feedback = (obj.get("feedback", "") or "").strip() or DEFAULT_REJECT_FEEDBACK
        decision = {"behavior": "deny", "message": feedback, "interrupt": False}
    elif action == "reject_stop":
        feedback = (obj.get("feedback", "") or "").strip() or DEFAULT_STOP_FEEDBACK
        decision = {"behavior": "deny", "message": feedback, "interrupt": True}
    else:
        return None
    return {"hookSpecificOutput": {"hookEventName": "PermissionRequest", "decision": decision}}


def main() -> int:
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except Exception:
        return 0

    tin = payload.get("tool_input", {}) or {}
    plan = tin.get("plan", "") or ""
    cwd = payload.get("cwd", "") or ""
    session = payload.get("session_id", "") or ""
    display_plan, embedded_visual_spec = extract_embedded_visual_spec(plan)
    approve_updated_input = None
    if display_plan != plan:
        approve_updated_input = dict(tin)
        approve_updated_input["plan"] = display_plan

    if not is_armed_and_consume(cwd):
        return 0  # dormant -> normal terminal approval

    try:
        ai_html = load_ai_page(cwd)
        if ai_html is not None:
            page = inject_controls(ai_html).encode("utf-8")
        else:
            legacy_visual_spec = load_visual_spec(cwd)
            visual_spec = embedded_visual_spec or legacy_visual_spec
            page = build_static_page(display_plan, cwd, session, visual_spec).encode("utf-8")
    except Exception:
        return 0  # rendering failed -> passthrough

    result = {"decision": None}
    got = threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def _send(self, code, ctype, body):
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.path == "/" or self.path.startswith("/?"):
                self._send(200, "text/html; charset=utf-8", page)
            else:
                self.send_response(404)
                self.end_headers()

        def do_POST(self):
            if self.path != "/decision":
                self.send_response(404)
                self.end_headers()
                return
            try:
                n = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(n) or b"{}")
            except Exception:
                body = {}
            result["decision"] = body
            self._send(200, "application/json", b'{"ok":true}')
            got.set()

    try:
        bind_port = int(os.environ.get("PLAN_REVIEW_PORT", "0"))
        httpd = HTTPServer(("127.0.0.1", bind_port), Handler)
    except Exception:
        return 0

    port = httpd.server_address[1]
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:%d/" % port

    if os.environ.get("PLAN_REVIEW_NO_BROWSER") != "1":
        opened = False
        try:
            opened = bool(webbrowser.open(url))
        except Exception:
            opened = False
        if not opened:
            try:
                httpd.shutdown()
            except Exception:
                pass
            return 0

    got.wait()
    try:
        httpd.shutdown()
    except Exception:
        pass

    out = to_decision(result["decision"], approve_updated_input)
    if out is None:
        return 0
    sys.stdout.write(json.dumps(out))
    sys.stdout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
