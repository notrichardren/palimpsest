# Palimpsest

Claude Code history viewer. Reads `~/.claude/projects/` directly. Zero dependencies beyond Python 3.

## Run

```bash
python3 server.py
# http://localhost:4523
# SSH: ssh -L 4523:localhost:4523 <host>
```

Port/host: `PORT=8080 HOST=0.0.0.0 python3 server.py`

## Features

- **Recent / Folders**: two sidebar views — all sessions by recency, or browse by project
- **Search**: full-text across all conversations. UUID queries hit a fast path (~30ms vs ~900ms)
- **In-conversation search**: highlight + scroll to matches within the current conversation
- **Resume**: each session has a clipboard icon that copies `claude --dangerously-skip-permissions --resume <id>`
- **Star / Rename**: inline in the sidebar (☆ and ✎). Persisted in `~/.palimpsest/meta.json`. Starred sessions float to top. Rename also works from the header — click "Rename" to edit the title in-place
- **Export**: download any conversation as `.md`
- **Filters**: toggle User / Assistant / Tools / Thinking / Results. Thinking and Results off by default
- **Theme**: dark/light, persisted in localStorage
- **Edit diffs**: red/green inline, expanded by default. Write content shown in green
- **Scroll**: conversations scroll to bottom on load. 200px bottom padding so you can scroll past the last message
- **Lightweight**: two files, no build step, no dependencies — easy to add features via Claude Code

## For Claude Code

The entire app is two files — `server.py` (API) and `templates/index.html` (UI). No framework, no build step, no node_modules.

**Data source:** `~/.claude/projects/<encoded-path>/<session-id>.jsonl`. Each JSONL file is one conversation. Lines are `{"type": "user"|"assistant", "message": {"role": ..., "content": ...}, ...}`. Tool use is `{"type": "tool_use", "name": "Bash", "input": {"command": "..."}}` inside assistant content arrays. Tool results come as separate user messages with `{"type": "tool_result", "tool_use_id": "..."}`.

**Metadata:** `~/.palimpsest/meta.json` stores `{"starred": {"<sid>": true}, "names": {"<sid>": "custom name"}}`. Additive only — new sessions just don't have entries. Orphaned entries are harmless.

**Adding features:** The server is a single `HTTPServer` subclass with `do_GET`/`do_POST`. Add a route, add a handler function. The frontend is vanilla JS in a `<script>` tag — `api(path)` fetches JSON, `post(path, body)` sends JSON. Messages render in `openConv()`. Session list renders in `sessionHTML()`. All state is in the `state` object.

**Session cache:** The server reads `.session_cache.json` in each project dir for fast metadata (summary, message count, timestamps) and falls back to reading the first user message from the JSONL.

## Layout

```
server.py              # API + static server (single file, no deps)
templates/index.html   # entire UI (single file, no build step)
~/.palimpsest/         # stars, renames (created on first use)
```

## API

GET (JSON):

```
/api/sessions              # all sessions (starred first, then recency)
/api/sessions?project=ID   # sessions for one project
/api/projects              # project list
/api/conversation/<sid>    # full parsed conversation
/api/search?q=...          # search (fast path for UUIDs)
/api/export/<sid>          # markdown download
/api/meta                  # star/rename metadata
```

POST (JSON body):

```
/api/star    {"session_id": "..."}                 # toggle star
/api/rename  {"session_id": "...", "name": "..."}  # set/clear name
```
