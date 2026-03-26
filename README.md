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
