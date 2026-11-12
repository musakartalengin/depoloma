# Depoloma

A disk space analyzer: a Python (standard library only) scanner + local web UI
(plain HTML/CSS/JS, no build step). Scanning is read-only; the only thing it can delete is
cache folders the user ticked and confirmed. See `README.md` for what it does.

## The one rule

**Depoloma deletes only caches, and only what the user ticked and confirmed in the window.**
Everything else — scanning, reports, every other endpoint — never deletes, moves, renames or modifies user files.

- All deleting lives in `depoloma/cleaner.py`. Don't add deleting/moving code anywhere else, and no
  command-line, headless or agent path for it: a person must see the list and confirm it.
- A folder is eligible only if its rule in `rules.py` has `clean=True`. Give that flag only to a `safe`
  folder whose **entire** content is disposable and comes back by itself (no settings, credentials,
  installed tools, or anything needing a manual command to restore). When in doubt, leave it off.
- Don't loosen the checks in `cleaner.py` (own profile only, link checks, one-time plan token, skip files
  in use, `keep_days` for temp, protected sub-folders) unless the user explicitly asks.
- Every clean-up is appended to `cleanup-log.txt` in `system.data_dir()`. Keep it: it is how the user answers
  "what did I delete?". A failing log write must never stop a clean-up. Dev/sandbox instances get their own
  `log_path` so test runs never land in the user's real log.
- AI coding tools are off limits: their folders hold the user's context (chat history, sessions, memory,
  scratchpads). Rules `ai_context` / `ai_app` are `keep`; nothing inside them is ever offered, caches included.
  When you learn of another such tool, add its folders there.
- A folder's name proves nothing. `app_cache` is `generic=True`: it never applies beneath a guarded folder
  (any `keep` rule, installed programs, site-packages…) and the folder must not look like a profile, a database
  or program code (`rules.looks_like_data`, `Cleaner._holds_data`). Known impostors go into `not_a_cache`.
- Games, projects, downloads, VMs, `node_modules` and the like get **no** delete button; the app explains how.
- While developing, never run a clean-up against real folders. Test in temp folders (the tests do).

## Run

- `python -m depoloma` — opens the window (app-mode Edge/Chrome, else a browser tab)
- `python -m depoloma --report [PATH]` — headless scan, text report on stdout (use this to read results from a terminal)
- `python -m depoloma --no-open --keep --port 47821` — server only, for development
- `python -m unittest discover -s tests` — tests (stdlib `unittest`, temp folders only)

## Layout

- `depoloma/scanner.py` — threaded directory walk → in-memory size tree (`Node`), project detection
- `depoloma/winfs.py` — Windows fast directory listing (ctypes), volumes, registry facts
- `depoloma/rules.py` — the knowledge base: one `R(...)` entry per known folder kind, texts in `tr` and `en`
- `depoloma/insights.py` — turns a finished scan into findings / categories / hotspots (JSON for the UI)
- `depoloma/cleaner.py` — the only code that deletes: validates a plan, empties confirmed cache folders
- `depoloma/server.py` — localhost HTTP API (token + Host check) and SSE progress
- `depoloma/system.py` — volumes, reveal-in-file-manager, app window, WSL `du`
- `depoloma/web/` — `index.html`, `app.css`, `app.js`, `i18n.js` (every UI string exists in `tr` and `en`)

## Conventions

- No third-party dependencies, Python 3.8 compatible (no `match`, no `X | Y` annotations at runtime).
- Names coming from the disk go into the DOM as text (`textContent`), never as HTML.
- Sizes are bytes allocated on disk. Category colours in `app.css` are a validated set in a fixed order —
  don't reorder them or add a seventh hue.
- New rule → add both languages (title, what, why, how); `tests` check that no text is missing
  and that every `clean=True` rule stays anchored inside the user profile.
- Windows, Ubuntu/Linux and macOS share one code base. UI strings that differ outside Windows have a twin key
  ending in `.nix` in `i18n.js` (picked automatically). Linux behaviour is tested without a Linux machine by
  `UbuntuSimulationTests` (an in-memory POSIX filesystem); extend that tree when you add Linux rules.
