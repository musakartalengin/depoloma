"""Local web server behind the Depoloma window.

Binds to 127.0.0.1 only. Every API call needs the random token baked into
the page, and the Host header must be the local address, so other websites
(or other machines) cannot query what is on your disk.

The API can: start/cancel a scan, read results, show an item in the file
manager, and measure a WSL distribution — all read-only.

The one exception is the clean-up of cache folders (see cleaner.py): the page
asks for a plan, the server decides by itself what is safe and returns the
exact list, and only that list can be run after the user confirmed it. Nothing
else in the API deletes, moves or changes anything.
"""
from __future__ import annotations

import json
import os
import secrets
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlsplit

from . import __version__, cleaner, insights, rules, system
from .scanner import Scanner

WEB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
RECENT_DAYS = 7             # "you used this program within the last week" → extra caution before cleaning
STATIC = {
    "/app.css": ("app.css", "text/css; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/i18n.js": ("i18n.js", "text/javascript; charset=utf-8"),
    "/icon.svg": ("icon.svg", "image/svg+xml"),
}


class App(object):
    def __init__(self, auto_exit=True, argv=None):
        self.token = secrets.token_urlsafe(24)
        self.auto_exit = auto_exit
        self.argv = argv or []
        self.rules = rules.RuleSet(home=system.home())
        self.linux_rules = rules.RuleSet("linux")
        self.cleaner = cleaner.Cleaner(self.rules, [system.home()],   # may only ever touch the user's own profile
                                       log_path=os.path.join(system.data_dir(), "cleanup-log.txt"))
        self.scan_options = {}
        self.scanner = None
        self.summary = None
        self.lock = threading.Lock()
        self.wsl_jobs = {}
        self.clients = 0
        self.ever_connected = False
        self.last_seen = time.time()
        self.quit_at = 0.0
        self.server = None
        self._volumes = None

    # ── facts ─────────────────────────────────────────────────────────────

    def volumes(self, refresh=False):
        if self._volumes is None or refresh:
            self._volumes = system.volumes()
        return self._volumes

    def meta(self):
        texts = self.linux_rules.texts()
        texts.update(self.rules.texts())
        sudo = ""
        if not system.IS_WIN:
            # how to start this very installation with root rights (to see protected folders)
            parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            sudo = "cd '%s' && sudo '%s' -m depoloma --no-open" % (parent, sys.executable)
        return {
            "sudo": sudo,
            "version": __version__,
            "platform": self.rules.platform,
            "elevated": system.is_elevated(),
            "home": system.home(),
            "sep": os.sep,
            "volumes": self.volumes(refresh=True),
            "rules": texts,
            "cats": list(rules.CATS),
            "wsl": bool(system.IS_WIN),
            "apps": not system.IS_MAC,                 # Windows uninstall list, or apt / snap / flatpak
            "canClean": True,
            "cleanLog": bool(self.cleaner.log_path) and os.path.isfile(self.cleaner.log_path),
        }

    # ── scanning ──────────────────────────────────────────────────────────

    def start_scan(self, roots):
        roots = [r for r in roots if isinstance(r, str) and os.path.isdir(r)]
        if not roots:
            raise ValueError("no valid folder to scan")
        with self.lock:
            if self.scanner is not None and self.scanner.state == "scanning":
                raise RuntimeError("a scan is already running")
            if self.cleaner.busy:
                raise RuntimeError("a clean-up is running")
            self.summary = None
            self.scanner = Scanner(roots, ruleset=self.rules, **self.scan_options)
            self.scanner.state = "scanning"
            self.scanner.started = time.time()
        threading.Thread(target=self._scan, args=(self.scanner,), name="depoloma-scan-main", daemon=True).start()

    def _scan(self, scanner):
        try:
            scanner.run()
            if scanner.state in ("done", "cancelled"):
                summary = insights.build_summary(scanner, self.volumes(refresh=True), can_clean=self.cleaner.offerable,
                                                 last_used=self.last_used(scanner))
                with self.lock:
                    if self.scanner is scanner:
                        self.summary = summary
        except Exception as exc:                                 # keep the UI informed
            scanner.error = scanner.error or "%s: %s" % (type(exc).__name__, exc)
            scanner.state = "error"

    def status(self):
        sc = self.scanner
        if sc is None:
            return {"state": "idle"}
        st = sc.progress()
        if st["state"] in ("done", "cancelled") and self.summary is None:
            st["state"] = "analyzing"
        st["roots"] = sc.roots
        target = 0
        for v in self.volumes():
            for r in sc.roots:
                if os.path.normcase(v["path"]) == os.path.normcase(r):
                    target += v["used"]
        st["target"] = target
        return st

    def node(self, node_id, deep):
        sc = self.scanner
        if sc is None or not (0 <= node_id < len(sc.nodes)):
            return None
        return insights.node_json(sc, sc.nodes[node_id], deep)

    # ── cleaning (the only thing here that deletes; see cleaner.py) ──────────

    def clean_plan(self, node_ids):
        sc = self.scanner
        if sc is None or sc.state not in ("done", "cancelled") or self.summary is None:
            raise RuntimeError("scan first")
        if self.cleaner.busy:
            raise RuntimeError("a clean-up is already running")
        plan = self.cleaner.plan(sc, node_ids)
        plan["running"] = system.running_apps([t["path"] for t in plan["targets"]])
        # When did the user last work in the program each folder belongs to? The UI warns about recent ones.
        used = self.last_used(sc)
        for t in plan["targets"]:
            t["app"], t["used"] = used(t["path"], t.get("newest") or 0)
        plan["recentDays"] = RECENT_DAYS
        return plan

    def last_used(self, sc):
        """Returns f(path, newest) → (program label, when the user last touched that program's data).

        A cache can be weeks old while its program was used an hour ago; what matters for
        "be careful, you were just working in this" is the program, so we look at the
        newest change anywhere in the program's own folder."""
        seen = {}

        def lookup(path, newest):
            for base in self.cleaner.bases:
                found = system.app_of(path, base)
                if found is None:
                    continue
                label, folder = found
                if folder not in seen:
                    node = sc.find(folder)
                    seen[folder] = node.newest if node is not None else 0
                return label, max(newest, seen[folder])
            return "", newest
        return lookup

    def clean_run(self, token, lang="en"):
        sc = self.scanner
        if sc is not None and sc.state == "scanning":
            raise RuntimeError("a scan is running")
        self.cleaner.start(str(token or ""), lang=str(lang or "en"))

    def show_clean_log(self):
        """Open the file manager at the clean-up log. Only that one file — never a path from the page."""
        path = self.cleaner.log_path
        return bool(path) and os.path.isfile(path) and system.reveal(path)

    # ── extras ────────────────────────────────────────────────────────────

    def apps(self):
        sc = self.scanner
        out = []
        for p in system.installed_programs():
            item = dict(p)
            item["size"] = p["estimated"]
            item["id"] = None
            item["measured"] = bool(p.get("exact"))      # e.g. snaps: the size of their files on disk
            loc = p["location"]
            if not item["measured"] and sc is not None and loc and len(loc) > 3 and sc.state in ("done", "cancelled"):
                node = sc.find(loc)
                if node is not None and node.size:
                    item["size"] = node.size
                    item["id"] = node.id
                    item["measured"] = True
            out.append(item)
        out.sort(key=lambda a: -a["size"])
        return out

    def wsl(self):
        distros = system.wsl_list()
        for d in distros:
            job = self.wsl_jobs.get(d["name"])
            d["job"] = {"state": job["state"], "error": job.get("error", "")} if job else None
        return distros

    def wsl_start(self, name):
        if name not in [d["name"] for d in system.wsl_list()]:
            raise ValueError("unknown distribution")
        job = self.wsl_jobs.get(name)
        if job and job["state"] == "running":
            return
        job = self.wsl_jobs[name] = {"state": "running", "started": time.time()}

        def run():
            try:
                res = system.wsl_scan(name)
                self._label_tree(res["tree"])
                job["result"] = res
                job["state"] = "done"
            except Exception as exc:
                job["error"] = str(exc)[:400]
                job["state"] = "error"
        threading.Thread(target=run, name="depoloma-wsl", daemon=True).start()

    def _label_tree(self, root):
        """Attach the matching Linux rule to every folder of a `du` tree."""
        stack = [(root, None)]
        while stack:
            n, inherited = stack.pop()
            r = self.linux_rules.match_path(n["path"]) if n["path"] != "/" else None
            if r is None:
                r = inherited
            n["rule"] = r.id if r is not None and not r.hidden else None
            child = r.child if r is not None else None
            for c in n["children"]:
                stack.append((c, child))

    def reveal(self, path):
        if not isinstance(path, str) or not path:
            return False
        norm = os.path.normcase(os.path.abspath(path))
        allowed = [v["path"] for v in self.volumes()]
        if self.scanner is not None:
            allowed += self.scanner.roots
        if not any(norm.startswith(os.path.normcase(a)) for a in allowed):
            return False
        return system.reveal(path)


def _json_bytes(obj):
    return json.dumps(obj, separators=(",", ":")).encode("ascii")


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    server_version = "Depoloma/" + __version__
    app = None

    def log_message(self, fmt, *args):              # keep the console quiet
        pass

    # ── helpers ───────────────────────────────────────────────────────────

    def _host_ok(self):
        host = (self.headers.get("Host") or "").lower()
        port = self.server.server_address[1]
        return host in ("127.0.0.1:%d" % port, "localhost:%d" % port)

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _json(self, obj, code=200):
        self._send(code, _json_bytes(obj))

    def _error(self, code, message):
        self._json({"error": message}, code)

    def _authorised(self, query):
        token = self.headers.get("X-Depoloma-Token") or (query.get("t") or [""])[0]
        return secrets.compare_digest(token, self.app.token)

    def _body(self):
        try:
            n = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            n = 0
        if n <= 0 or n > 1 << 20:
            return {}
        try:
            data = json.loads(self.rfile.read(n).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except ValueError:
            return {}

    # ── routes ────────────────────────────────────────────────────────────

    def do_GET(self):
        if not self._host_ok():
            return self._error(403, "bad host")
        url = urlsplit(self.path)
        path = url.path
        query = parse_qs(url.query)
        app = self.app
        if path in ("/", "/index.html"):
            try:
                with open(os.path.join(WEB_DIR, "index.html"), "r", encoding="utf-8") as fh:
                    html = fh.read().replace("__TOKEN__", app.token).replace("__VERSION__", __version__)
            except OSError:
                return self._error(500, "ui files missing")
            csp = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; "
                   "script-src 'self'; connect-src 'self'; base-uri 'none'; form-action 'none'")
            return self._send(200, html.encode("utf-8"), "text/html; charset=utf-8", {"Content-Security-Policy": csp})
        if path in STATIC:
            name, ctype = STATIC[path]
            try:
                with open(os.path.join(WEB_DIR, name), "rb") as fh:
                    return self._send(200, fh.read(), ctype)
            except OSError:
                return self._error(404, "not found")
        if not path.startswith("/api/"):
            return self._error(404, "not found")
        if not self._authorised(query):
            return self._error(403, "bad token")
        try:
            if path == "/api/meta":
                return self._json(app.meta())
            if path == "/api/status":
                return self._json(app.status())
            if path == "/api/summary":
                if app.summary is None:
                    return self._error(409, "no finished scan")
                return self._json(app.summary)
            if path == "/api/node":
                node = app.node(int((query.get("id") or ["-1"])[0]), (query.get("deep") or ["0"])[0] == "1")
                if node is None:
                    return self._error(404, "unknown folder")
                return self._json(node)
            if path == "/api/clean/status":
                return self._json(app.cleaner.status())
            if path == "/api/apps":
                return self._json({"apps": app.apps()})
            if path == "/api/wsl":
                return self._json({"distros": app.wsl()})
            if path == "/api/wsl/result":
                job = app.wsl_jobs.get((query.get("name") or [""])[0])
                if not job:
                    return self._error(404, "no scan for this distribution")
                return self._json({"state": job["state"], "error": job.get("error", ""), "result": job.get("result")})
            if path == "/api/events":
                return self._events()
        except Exception as exc:                                  # pragma: no cover - defensive
            return self._error(500, "%s: %s" % (type(exc).__name__, exc))
        return self._error(404, "not found")

    def do_POST(self):
        if not self._host_ok():
            return self._error(403, "bad host")
        url = urlsplit(self.path)
        if not self._authorised(parse_qs(url.query)):
            return self._error(403, "bad token")
        app = self.app
        body = self._body()
        path = url.path
        try:
            if path == "/api/scan":
                app.start_scan(body.get("roots") or [])
                return self._json({"ok": True})
            if path == "/api/cancel":
                if app.scanner is not None:
                    app.scanner.cancel()
                return self._json({"ok": True})
            if path == "/api/reveal":
                return self._json({"ok": app.reveal(body.get("path"))})
            if path == "/api/clean/plan":
                nodes = body.get("nodes")
                return self._json(app.clean_plan(nodes if isinstance(nodes, list) else []))
            if path == "/api/clean/run":
                app.clean_run(body.get("token"), body.get("lang"))
                return self._json({"ok": True})
            if path == "/api/clean/log":
                return self._json({"ok": app.show_clean_log()})
            if path == "/api/clean/cancel":
                app.cleaner.cancel()
                return self._json({"ok": True})
            if path == "/api/wsl/scan":
                app.wsl_start(str(body.get("name") or ""))
                return self._json({"ok": True})
            if path == "/api/elevate":
                ok = system.relaunch_elevated(app.argv)
                if ok:
                    app.quit_at = time.time() + 1.5
                return self._json({"ok": ok})
            if path == "/api/quit":
                app.quit_at = time.time() + 0.3
                return self._json({"ok": True})
        except (ValueError, RuntimeError) as exc:
            return self._error(400, str(exc))
        except Exception as exc:                                  # pragma: no cover - defensive
            return self._error(500, "%s: %s" % (type(exc).__name__, exc))
        return self._error(404, "not found")

    def _events(self):
        """Server-sent events: live scan progress, and proof that the window is still open."""
        app = self.app
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        self.end_headers()
        self.close_connection = True
        with app.lock:
            app.clients += 1
            app.ever_connected = True
        last = None
        idle = 0.0
        try:
            while True:
                st = app.status()
                busy = st["state"] in ("scanning", "analyzing")
                payload = _json_bytes(st)
                if payload != last or idle >= 2.0:
                    self.wfile.write(b"data: " + payload + b"\n\n")
                    self.wfile.flush()
                    last = payload
                    idle = 0.0
                step = 0.25 if busy else 0.5
                time.sleep(step)
                idle += step
        except (OSError, ValueError):
            pass
        finally:
            with app.lock:
                app.clients -= 1
                app.last_seen = time.time()
            self.close_connection = True


class _Server(ThreadingHTTPServer):
    daemon_threads = True
    allow_reuse_address = False

    def handle_error(self, request, client_address):            # browsers drop connections all the time
        pass


def serve(app, port=0):
    """Start the server (in a background thread) and return it."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = _Server(("127.0.0.1", port), handler)
    app.server = server
    threading.Thread(target=server.serve_forever, name="depoloma-http", daemon=True).start()
    return server


def wait(app, grace=12.0):
    """Block until the user quits: Ctrl+C, the quit button, or the window was closed."""
    started = time.time()
    try:
        while True:
            time.sleep(0.5)
            now = time.time()
            if app.quit_at and now >= app.quit_at:
                break
            if not app.auto_exit:
                continue
            if app.ever_connected:
                if app.clients <= 0 and now - app.last_seen > grace and not app.cleaner.busy:
                    sc = app.scanner
                    if sc is None or sc.state != "scanning":
                        break
            elif now - started > 300:
                break                                   # the window never showed up: don't linger in the background
    except KeyboardInterrupt:
        pass
    finally:
        if app.scanner is not None:
            app.scanner.cancel()
        try:
            app.server.shutdown()
        except Exception:
            pass
