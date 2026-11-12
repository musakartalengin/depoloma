"""Depoloma command line: `python -m depoloma` (or just `depoloma`)."""
from __future__ import annotations

import argparse
import json
import os
import sys

from . import __version__

DEFAULT_PORT = 47821


def _say(*parts):
    try:
        print(*parts, flush=True)
    except Exception:                       # pythonw has no console
        pass


def _default_roots():
    from . import system
    vols = system.volumes()
    for v in vols:
        if v.get("system"):
            return [v["path"]]
    return [vols[0]["path"]] if vols else [system.home()]


def _headless(args):
    """Scan without a window and print a report (handy for terminals and AI agents)."""
    from . import insights, report, rules, system
    from .scanner import Scanner

    try:                                    # piped output (agents, files) should be UTF-8, not the legacy code page
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    system.prepare_privileges()
    roots = [os.path.abspath(r) for r in args.paths] or _default_roots()
    for r in roots:
        if not os.path.isdir(r):
            _say("Not a folder: %s" % r)
            return 2
    ruleset = rules.RuleSet(home=system.home())
    scanner = Scanner(roots, ruleset=ruleset, threads=args.threads)
    _say("Depoloma %s — scanning %s (read-only)…" % (__version__, ", ".join(roots)))
    scanner.run()
    summary = insights.build_summary(scanner, system.volumes())
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(summary, fh, ensure_ascii=False, indent=1)
        _say("Wrote %s" % args.json)
    if args.report or not args.json:
        texts = rules.RuleSet("linux").texts()
        texts.update(ruleset.texts())
        text = report.text_report(summary, texts, args.lang or system.system_lang(), platform=ruleset.platform)
        sys.stdout.write(text + "\n")
    return 0


def main(argv=None):
    p = argparse.ArgumentParser(
        prog="depoloma",
        description="See where your disk space went. Scanning only reads; nothing is deleted unless you "
                    "tick it and confirm it in the window (cache folders only).")
    p.add_argument("paths", nargs="*", help="folders/drives to scan (default: choose in the window)")
    p.add_argument("--report", action="store_true", help="no window: scan and print a text report")
    p.add_argument("--json", metavar="FILE", help="no window: scan and write the full analysis as JSON")
    p.add_argument("--lang", choices=("tr", "en"), help="report language (default: system language)")
    p.add_argument("--port", type=int, default=None, help="port for the local UI (default: %d, or a free one)" % DEFAULT_PORT)
    p.add_argument("--tab", action="store_true", help="open in a normal browser tab instead of an app window")
    p.add_argument("--no-open", action="store_true", help="don't open a window, just print the address")
    p.add_argument("--keep", action="store_true", help="keep running after the window is closed")
    p.add_argument("--threads", type=int, default=None, help="scanner threads (default: up to 8)")
    p.add_argument("--version", action="version", version="depoloma " + __version__)
    args = p.parse_args(argv)

    if args.report or args.json:
        return _headless(args)

    from . import server, system

    system.prepare_privileges()
    app = server.App(auto_exit=not args.keep, argv=list(sys.argv[1:] if argv is None else argv))
    srv = None
    # A fixed default port keeps the theme/language choice (stored per address by
    # the browser) between runs; if it is taken, any free port will do.
    for port in ([args.port] if args.port is not None else [DEFAULT_PORT, 0]):
        try:
            srv = server.serve(app, port)
            break
        except OSError as exc:
            err = exc
    if srv is None:
        _say("Cannot start the local server: %s" % err)
        return 1
    url = "http://127.0.0.1:%d/" % srv.server_address[1]
    roots = [os.path.abspath(r) for r in args.paths if os.path.isdir(r)]
    if roots:
        app.start_scan(roots)
    mode = system.open_ui(url, "none" if args.no_open else ("tab" if args.tab else "app"))
    _say("Depoloma %s  →  %s" % (__version__, url))
    if mode == "none":
        _say("Open the address above in a browser. Press Ctrl+C to quit.")
        app.auto_exit = False
    else:
        _say("The window is open. Close it (or press Ctrl+C here) to quit.")
    server.wait(app)
    return 0


if __name__ == "__main__":
    sys.exit(main())
