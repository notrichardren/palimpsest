#!/usr/bin/env python3
"""Palimpsest — Claude Code History Viewer"""

import json, os, re
from pathlib import Path
from datetime import datetime, timezone
from http.server import HTTPServer, SimpleHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

CLAUDE_DIR = Path.home() / ".claude"
PROJECTS_DIR = CLAUDE_DIR / "projects"
META_DIR = Path.home() / ".palimpsest"
META_FILE = META_DIR / "meta.json"
PORT = int(os.environ.get("PORT", "4523"))
HOST = os.environ.get("HOST", "0.0.0.0")

# ── Metadata (stars, renames) ────────────────────────

def load_meta():
    if META_FILE.exists():
        try: return json.loads(META_FILE.read_text())
        except: pass
    return {"starred": {}, "names": {}}

def save_meta(meta):
    META_DIR.mkdir(parents=True, exist_ok=True)
    META_FILE.write_text(json.dumps(meta, indent=2))

# ── Data helpers ─────────────────────────────────────

def get_cwd(filepath):
    try:
        with open(filepath) as f:
            for line in f:
                if not line.strip(): continue
                d = json.loads(line)
                if d.get("cwd"): return d["cwd"]
    except: pass
    return None

def get_summary(filepath):
    try:
        with open(filepath) as f:
            for line in f:
                if not line.strip(): continue
                d = json.loads(line)
                if d.get("type") == "user" and d.get("message", {}).get("role") == "user":
                    c = d["message"].get("content", "")
                    if isinstance(c, str): return c[:300]
                    if isinstance(c, list):
                        for b in c:
                            if isinstance(b, dict) and b.get("type") == "text":
                                return b.get("text", "")[:300]
    except: pass
    return None

def load_cache(project_dir):
    for name in [".session_cache.json", "sessions-index.json"]:
        p = project_dir / name
        if p.exists():
            try: return json.loads(p.read_text())
            except: pass
    return None

def all_sessions():
    sessions = []
    if not PROJECTS_DIR.exists(): return sessions
    meta = load_meta()
    for pd in PROJECTS_DIR.iterdir():
        if not pd.is_dir(): continue
        cache = load_cache(pd)
        cwd_cache = None
        for f in pd.glob("*.jsonl"):
            sid = f.stem
            st = f.stat()
            summary, mcount, ftime, ltime = None, None, None, None
            if cache and "entries" in cache:
                e = cache["entries"].get(str(f))
                if e:
                    s = e.get("session") or {}
                    summary = s.get("summary") or e.get("first_user_content")
                    mcount = s.get("message_count")
                    ftime = s.get("first_message_time")
                    ltime = s.get("last_message_time")
            if not summary:
                summary = get_summary(f)
            if not cwd_cache:
                cwd_cache = get_cwd(f)
            project_path = cwd_cache or ("/" + pd.name.lstrip("-").replace("-", "/"))
            sessions.append({
                "session_id": sid,
                "file_path": str(f),
                "project_id": pd.name,
                "project_path": project_path,
                "project_name": Path(project_path).name,
                "summary": summary or f"Session {sid[:8]}...",
                "message_count": mcount,
                "modified": ltime or datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "modified_ts": st.st_mtime,
                "starred": meta["starred"].get(sid, False),
                "custom_name": meta["names"].get(sid),
            })
    # Starred first, then by recency
    sessions.sort(key=lambda s: (not s["starred"], -s["modified_ts"]))
    return sessions

def all_projects():
    projects = {}
    for s in all_sessions():
        pid = s["project_id"]
        if pid not in projects:
            projects[pid] = {
                "id": pid, "path": s["project_path"], "name": s["project_name"],
                "count": 0, "last_modified": s["modified"], "last_ts": s["modified_ts"],
            }
        projects[pid]["count"] += 1
    return sorted(projects.values(), key=lambda p: p["last_ts"], reverse=True)

def parse_conversation(filepath):
    messages = []
    with open(filepath) as f:
        for line in f:
            if not line.strip(): continue
            try: d = json.loads(line)
            except: continue
            t = d.get("type")
            if t in ("file-history-snapshot", "queue-operation", "progress"): continue
            msg = d.get("message", {})
            content = msg.get("content", d.get("content", ""))
            if t == "user":
                if isinstance(content, list) and any(isinstance(b, dict) and b.get("type") == "tool_result" for b in content):
                    for b in content:
                        if isinstance(b, dict) and b.get("type") == "tool_result":
                            rc = b.get("content", "")
                            if isinstance(rc, list):
                                rc = "\n".join(c.get("text","") for c in rc if isinstance(c,dict) and c.get("type")=="text")
                            messages.append({"role": "tool_result", "tool_use_id": b.get("tool_use_id"), "content": str(rc), "is_error": b.get("is_error", False)})
                    continue
                if isinstance(content, list):
                    content = "\n".join(b.get("text","") for b in content if isinstance(b,dict) and b.get("type")=="text")
                messages.append({"role": "user", "content": str(content), "ts": d.get("timestamp")})
            elif t == "assistant":
                blocks = []
                if isinstance(content, str):
                    blocks.append({"type": "text", "text": content})
                elif isinstance(content, list):
                    for b in content:
                        if not isinstance(b, dict): continue
                        bt = b.get("type")
                        if bt == "text": blocks.append({"type": "text", "text": b.get("text","")})
                        elif bt == "tool_use":
                            blocks.append({"type": "tool_use", "name": b.get("name",""), "id": b.get("id",""), "input": b.get("input",{})})
                        elif bt == "thinking":
                            blocks.append({"type": "thinking", "text": b.get("thinking","")})
                messages.append({"role": "assistant", "blocks": blocks, "model": msg.get("model",""), "ts": d.get("timestamp")})
            elif t == "summary":
                messages.append({"role": "summary", "content": d.get("summary",""), "ts": d.get("timestamp")})
    return messages

def export_markdown(sid):
    for s in all_sessions():
        if s["session_id"] != sid: continue
        msgs = parse_conversation(s["file_path"])
        lines = [f"# {s.get('custom_name') or s['summary'][:80]}", f"**Project:** {s['project_path']}  ", f"**Session:** `{sid}`  ", f"**Date:** {s['modified']}", "", "---", ""]
        tool_results = {m["tool_use_id"]: m for m in msgs if m["role"] == "tool_result"}
        for m in msgs:
            if m["role"] == "tool_result": continue
            if m["role"] == "user":
                lines += [f"## User", "", m["content"], ""]
            elif m["role"] == "assistant":
                lines.append("## Assistant")
                lines.append("")
                for b in m.get("blocks", []):
                    if b["type"] == "text":
                        lines += [b["text"], ""]
                    elif b["type"] == "tool_use":
                        summary = b["input"].get("command") or b["input"].get("file_path") or b["input"].get("pattern") or ""
                        lines.append(f"**{b['name']}**({summary})")
                        tr = tool_results.get(b["id"])
                        if tr:
                            content = tr["content"]
                            if len(content) > 2000: content = content[:2000] + "\n... (truncated)"
                            lines += ["```", content, "```", ""]
                        else:
                            lines.append("")
                    elif b["type"] == "thinking":
                        lines += ["<details><summary>Thinking</summary>", "", b["text"], "", "</details>", ""]
            elif m["role"] == "summary":
                lines += [f"> **Summary:** {m['content']}", ""]
        return "\n".join(lines)
    return None

UUID_RE = re.compile(r'^[0-9a-f]{4,}(?:-[0-9a-f]+)*$', re.IGNORECASE)

def search_by_uid(query):
    """Fast path: scan filenames directly instead of loading all session metadata."""
    ql = query.lower()
    results = []
    meta = load_meta()
    if not PROJECTS_DIR.exists(): return results
    for pd in PROJECTS_DIR.iterdir():
        if not pd.is_dir(): continue
        for f in pd.glob("*.jsonl"):
            sid = f.stem
            if ql not in sid.lower(): continue
            st = f.stat()
            cwd = get_cwd(f)
            project_path = cwd or ("/" + pd.name.lstrip("-").replace("-", "/"))
            summary = get_summary(f) or f"Session {sid[:8]}..."
            results.append({
                "session_id": sid, "file_path": str(f), "project_id": pd.name,
                "project_path": project_path, "project_name": Path(project_path).name,
                "summary": summary, "message_count": None,
                "modified": datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).isoformat(),
                "modified_ts": st.st_mtime,
                "starred": meta["starred"].get(sid, False),
                "custom_name": meta["names"].get(sid),
                "snippet": f"Session ID: {sid}",
            })
    results.sort(key=lambda s: s["modified_ts"], reverse=True)
    return results

def search_conversations(query, limit=50):
    # Fast path for UUID-like queries — direct filename match
    if UUID_RE.match(query.strip()):
        fast = search_by_uid(query.strip())
        if fast: return fast

    results = []
    ql = query.lower()
    for s in all_sessions():
        if ql in s["session_id"].lower():
            results.append({**s, "snippet": f"Session ID: {s['session_id']}"})
            if len(results) >= limit: break
            continue
        try:
            text = Path(s["file_path"]).read_text()
            if ql not in text.lower(): continue
            idx = text.lower().index(ql)
            start, end = max(0, idx-80), min(len(text), idx+len(query)+80)
            snippet = ("..." if start>0 else "") + text[start:end] + ("..." if end<len(text) else "")
            snippet = re.sub(r'[{}\[\]"\\]', '', snippet)[:200]
            results.append({**s, "snippet": snippet})
            if len(results) >= limit: break
        except: pass
    return results

# ── HTTP Server ──────────────────────────────────────

class Handler(SimpleHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        path = parsed.path
        qs = parse_qs(parsed.query)

        if path == "/api/sessions":
            project = qs.get("project", [None])[0]
            sessions = all_sessions()
            if project:
                sessions = [s for s in sessions if s["project_id"] == project]
            self.json_response(sessions)
        elif path == "/api/projects":
            self.json_response(all_projects())
        elif path.startswith("/api/conversation/"):
            sid = path.split("/")[-1]
            for s in all_sessions():
                if s["session_id"] == sid:
                    self.json_response({"meta": s, "messages": parse_conversation(s["file_path"])})
                    return
            self.json_response({"error": "not found"}, 404)
        elif path == "/api/search":
            q = qs.get("q", [""])[0]
            self.json_response(search_conversations(q) if q else [])
        elif path == "/api/meta":
            self.json_response(load_meta())
        elif path.startswith("/api/export/"):
            sid = path.split("/")[-1]
            md = export_markdown(sid)
            if md:
                body = md.encode()
                self.send_response(200)
                self.send_header("Content-Type", "text/markdown; charset=utf-8")
                self.send_header("Content-Disposition", f'attachment; filename="palimpsest-{sid[:8]}.md"')
                self.send_header("Content-Length", len(body))
                self.end_headers()
                self.wfile.write(body)
            else:
                self.json_response({"error": "not found"}, 404)
        elif path == "/":
            self.send_file("templates/index.html", "text/html")
        elif path.startswith("/static/"):
            fpath = Path(__file__).parent / path.lstrip("/")
            if fpath.exists():
                ct = "text/css" if path.endswith(".css") else "application/javascript" if path.endswith(".js") else "application/octet-stream"
                self.send_file(str(fpath), ct)
            else:
                self.send_error(404)
        else:
            self.send_error(404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length)) if length else {}

        if path == "/api/star":
            sid = body.get("session_id")
            meta = load_meta()
            meta["starred"][sid] = not meta["starred"].get(sid, False)
            save_meta(meta)
            self.json_response({"starred": meta["starred"][sid]})
        elif path == "/api/rename":
            sid = body.get("session_id")
            name = body.get("name", "").strip()
            meta = load_meta()
            if name:
                meta["names"][sid] = name
            else:
                meta["names"].pop(sid, None)
            save_meta(meta)
            self.json_response({"name": meta["names"].get(sid)})
        else:
            self.json_response({"error": "not found"}, 404)

    def json_response(self, data, code=200):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def send_file(self, filepath, content_type):
        body = Path(filepath).read_bytes()
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", len(body))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):
        pass

if __name__ == "__main__":
    print(f"\n  Palimpsest — Claude Code History Viewer")
    print(f"  http://localhost:{PORT}")
    print(f"  SSH: ssh -L {PORT}:localhost:{PORT} <host>")
    print(f"  Data: {META_DIR}\n")
    HTTPServer((HOST, PORT), Handler).serve_forever()
