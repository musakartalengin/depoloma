"""The only part of Depoloma that removes anything.

Scanning never deletes. This module empties *cache folders the user ticked and
confirmed*, and it is deliberately narrow:

* Only folders matched by a rule with `clean=True` (see rules.py): caches whose
  entire content is disposable and comes back by itself.
* Only inside the current user's own profile folder.
* The page asks for a plan; the server validates every folder itself and hands
  back exactly what it will do. Only that plan — by its one-time token — can be
  run, so what gets deleted is what was shown and confirmed.
* The folder itself stays; only its content goes.
* Links and junctions are never followed (the link is removed, never its target).
* Files in use are skipped, never forced. Sub-folders that belong to something
  worth keeping (a game, AI models, …) are left alone.
* Temp folders keep everything changed in the last week (`keep_days`).
* Every clean-up is written to a plain text log (folders, sizes, what was left alone),
  so "what did I delete, and when?" always has an answer.

There is no command-line switch for this, on purpose: deleting always needs a
person looking at the list.
"""
from __future__ import annotations

import os
import secrets
import shutil
import stat
import threading
import time

IS_WIN = os.name == "nt"
SEP = os.sep

if IS_WIN:
    from .winfs import extended
else:                                                    # pragma: no cover - POSIX
    def extended(path):
        return path

_ATTR_READONLY = 0x1
_ATTR_DIRECTORY = 0x10
_ATTR_REPARSE = 0x400
PLAN_TTL = 15 * 60          # a plan the user has not confirmed within 15 minutes is forgotten
MAX_TARGETS = 2000


def _norm(path):
    return os.path.normcase(os.path.abspath(path))


def _under(path, base):
    """True when `path` is strictly inside `base`."""
    p = _norm(path)
    b = _norm(base).rstrip(SEP)
    return bool(b) and p.startswith(b + SEP)


def _is_link(path):
    """Symlink, junction or any other reparse point. Unknown counts as a link (= hands off)."""
    try:
        st = os.lstat(path)
    except OSError:
        return True
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & _ATTR_REPARSE)


LOG_MAX = 2 << 20          # past 2 MB the log is renamed to *.old.txt and a new one is started

_LOG_TEXT = {
    "tr": {
        "start": "Temizlik başladı: %d klasör, planlanan %s",
        "end": {"done": "Bitti", "cancelled": "Durduruldu", "error": "Hata ile bitti"},
        "sum": "%s boşaldı, %d dosya silindi, %d atlandı (kullanımda / okunamadı), %d yeni öğe ve %d korunan klasöre dokunulmadı",
        "freed": "boşaldı", "skipped": "atlandı", "untouched": "dokunulmadı", "notrun": "sıra gelmedi",
        "rule": "kural", "free": "Boş alan: %s → %s",
    },
    "en": {
        "start": "Clean-up started: %d folders, planned %s",
        "end": {"done": "Finished", "cancelled": "Stopped", "error": "Ended with an error"},
        "sum": "%s freed, %d files deleted, %d skipped (in use / unreadable), %d recent items and %d protected folders left alone",
        "freed": "freed", "skipped": "skipped", "untouched": "left alone", "notrun": "not reached",
        "rule": "rule", "free": "Free space: %s → %s",
    },
}


def _size(n):
    if n is None:
        return "?"
    for unit in ("B", "KB", "MB", "GB"):
        if abs(n) < 1024 or unit == "GB":
            return ("%d %s" % (n, unit)) if unit == "B" else ("%.1f %s" % (n, unit))
        n /= 1024.0
    return "%.1f GB" % n                                        # pragma: no cover


def _stamp(t):
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(t))


class Cleaner(object):
    def __init__(self, ruleset, bases, log_path=None):
        self.rules = ruleset
        self.bases = [b for b in bases if b]
        self.log_path = log_path            # every clean-up is written here: what was emptied, when, how much
        self._plans = {}
        self._lock = threading.Lock()
        self._cancel = False
        self.job = None                      # status dict of the running / last run
        self._lang = "en"

    # ── what may be cleaned ───────────────────────────────────────────────

    def eligible(self, node, path):
        """Cheap check without touching the disk: a cleanable rule, inside the profile."""
        rule = node.rule
        return rule is not None and rule.clean and any(_under(path, b) for b in self.bases)

    def offerable(self, node, path):
        """Full check, used to decide whether the UI shows a tick box: everything `refusal` tests."""
        return self.eligible(node, path) and self.refusal(node.rule, path) is None

    def refusal(self, rule, path):
        """None when `path` may be emptied; otherwise the reason it may not."""
        if rule is None or not rule.clean:
            return "rule"
        base = None
        for b in self.bases:
            if _under(path, b):
                base = b
                break
        if base is None:
            return "outside"
        if not os.path.isdir(path):
            return "missing"
        # the folder and every folder between it and the profile must be real folders, not links
        probe = _norm(path)
        stop = _norm(base).rstrip(SEP)
        while len(probe) > len(stop):
            if _is_link(probe):
                return "link"
            probe = os.path.dirname(probe)
        again = self.rules.match_path(path, hidden=True)     # independent second opinion from the rule book
        if again is None or again.id != rule.id:
            return "mismatch"
        if rule.generic:
            # A rule that matched on the folder's NAME is double-checked on where it is and what is in it.
            if self.rules.guard_above(path, base) is not None:
                return "guarded"                              # inside a program, an AI tool, a `keep` folder
            if self._holds_data(path):
                return "not-cache"                            # a profile, a database or program code
        return None

    @staticmethod
    def _holds_data(path, depth=3, budget=1500):
        """Look a few levels into a folder that is named like a cache: does it hold anything that is
        not anonymous cache blobs (see rules.looks_like_data)? Unreadable counts as yes."""
        from .rules import looks_like_data
        stack = [(extended(path), 0)]
        while stack and budget > 0:
            folder, level = stack.pop()
            try:
                entries = list(os.scandir(folder))
            except OSError:
                return True
            budget -= len(entries)
            if looks_like_data(e.name for e in entries):
                return True
            if level < depth:
                for e in entries:
                    try:
                        st = e.stat(follow_symlinks=False)
                    except OSError:
                        continue
                    if stat.S_ISDIR(st.st_mode) and not getattr(st, "st_file_attributes", 0) & _ATTR_REPARSE:
                        stack.append((e.path, level + 1))
        return False

    # ── plan ──────────────────────────────────────────────────────────────

    def plan(self, scanner, node_ids):
        """Validate the folders the user ticked. Returns what would be emptied, with a one-time token."""
        if scanner is None or scanner.state not in ("done", "cancelled"):
            raise RuntimeError("no finished scan")
        targets, rejected, seen = [], [], set()
        for raw in list(node_ids)[:MAX_TARGETS]:
            try:
                nid = int(raw)
            except (TypeError, ValueError):
                continue
            if nid in seen or not (0 <= nid < len(scanner.nodes)):
                continue
            seen.add(nid)
            node = scanner.nodes[nid]
            path = node.path()
            why = self.refusal(node.rule, path)
            if why is not None:
                rejected.append({"path": path, "why": why})
                continue
            targets.append({"id": nid, "path": path, "size": node.size, "rule": node.rule.id,
                            "keepDays": node.rule.keep_days, "newest": node.newest})
        # a folder inside another selected folder would be emptied twice — keep the outer one
        targets.sort(key=lambda t: len(t["path"]))
        kept = []
        for t in targets:
            if not any(_under(t["path"], k["path"]) for k in kept):
                kept.append(t)
        kept.sort(key=lambda t: -t["size"])
        token = secrets.token_urlsafe(18)
        now = time.time()
        with self._lock:
            for old in [k for k, v in self._plans.items() if now - v["created"] > PLAN_TTL]:
                del self._plans[old]
            self._plans[token] = {"created": now, "targets": kept}
        return {"token": token, "targets": kept, "rejected": rejected, "total": sum(t["size"] for t in kept)}

    # ── run ───────────────────────────────────────────────────────────────

    @property
    def busy(self):
        return self.job is not None and self.job["state"] == "running"

    def start(self, token, lang="en"):
        """Run a confirmed plan in the background. A token works exactly once."""
        self._lang = lang if lang in _LOG_TEXT else "en"
        with self._lock:
            if self.busy:
                raise RuntimeError("a clean-up is already running")
            plan = self._plans.pop(token, None)
            if plan is None or time.time() - plan["created"] > PLAN_TTL:
                raise ValueError("this confirmation has expired; select again")
            self._cancel = False
            self.job = {"state": "running", "planned": sum(t["size"] for t in plan["targets"]), "freed": 0,
                        "files": 0, "dirs": 0, "skipped": 0, "kept": 0, "protected": 0, "current": "",
                        "started": time.time(), "elapsed": 0.0, "error": "",
                        "freeBefore": self._free(), "freeAfter": None, "log": self.log_path or "",
                        "targets": [dict(t, freed=0, skipped=0, done=False, why="") for t in plan["targets"]]}
        self._log_start(self.job)
        threading.Thread(target=self._run, name="depoloma-clean", daemon=True).start()

    def cancel(self):
        self._cancel = True

    def status(self):
        job = self.job
        if job is None:
            return {"state": "idle"}
        out = dict(job)
        if job["state"] == "running":
            out["elapsed"] = round(time.time() - job["started"], 1)
        return out

    def _free(self):
        try:
            return shutil.disk_usage(self.bases[0]).free
        except (OSError, IndexError):
            return None

    def _run(self):
        job = self.job
        try:
            for t in job["targets"]:
                if self._cancel:
                    break
                rule = self.rules.rules.get(t["rule"])
                why = self.refusal(rule, t["path"])            # checked again at the moment of deleting
                if why is not None:
                    t["why"] = why
                    t["done"] = True
                    continue
                self._empty(job, t, rule)
                t["done"] = True
            job["state"] = "cancelled" if self._cancel else "done"
        except Exception as exc:                                # pragma: no cover - defensive
            job["error"] = "%s: %s" % (type(exc).__name__, exc)
            job["state"] = "error"
        finally:
            job["current"] = ""
            job["elapsed"] = round(time.time() - job["started"], 1)
            job["freeAfter"] = self._free()
            self._log_end(job)

    # ── log: a plain text record of every clean-up, so "what did I delete?" always has an answer ──

    def _log(self, lines):
        """Append to the log. Never raises: a log that cannot be written must not stop or break a clean-up."""
        if not self.log_path:
            return
        try:
            os.makedirs(os.path.dirname(self.log_path), exist_ok=True)
            try:
                if os.path.getsize(self.log_path) > LOG_MAX:
                    old = self.log_path[:-4] + ".old.txt" if self.log_path.endswith(".txt") else self.log_path + ".old"
                    os.replace(self.log_path, old)              # the one older log is replaced, nothing else
            except OSError:
                pass
            with open(self.log_path, "a", encoding="utf-8", newline="") as fh:
                fh.write("".join(line + os.linesep for line in lines))
        except OSError:
            if self.job is not None:
                self.job["logError"] = True

    def _sz(self, n):
        text = _size(n)
        return text.replace(".", ",") if self._lang == "tr" else text   # 1,2 GB in Turkish, as on screen

    def _log_start(self, job):
        tx = _LOG_TEXT[self._lang]
        _size = self._sz
        lines = ["", "=== %s  %s" % (_stamp(job["started"]), tx["start"] % (len(job["targets"]), _size(job["planned"])))]
        for t in job["targets"]:
            lines.append("    %10s  %s  [%s: %s]" % (_size(t["size"]), t["path"], tx["rule"], t["rule"]))
        self._log(lines)

    def _log_end(self, job):
        tx = _LOG_TEXT[self._lang]
        _size = self._sz
        end = time.time()
        lines = ["--- %s  %s (%.0f s)" % (_stamp(end), tx["end"].get(job["state"], job["state"]), end - job["started"]),
                 "    " + tx["sum"] % (_size(job["freed"]), job["files"], job["skipped"], job["kept"], job["protected"])]
        for t in job["targets"]:
            if t["why"]:
                note = "%s (%s)" % (tx["untouched"], t["why"])
            elif not t["done"]:
                note = tx["notrun"]
            else:
                note = "%s %s" % (_size(t["freed"]), tx["freed"])
                if t["skipped"]:
                    note += ", %d %s" % (t["skipped"], tx["skipped"])
            lines.append("    %-28s  %s" % (note, t["path"]))
        if job["freeBefore"] is not None and job["freeAfter"] is not None:
            lines.append("    " + tx["free"] % (_size(job["freeBefore"]), _size(job["freeAfter"])))
        if job["error"]:
            lines.append("    " + job["error"])
        self._log(lines)

    def _protected(self, path, own_rule):
        """A sub-folder that is a finding of its own and not disposable (a game, AI models, a VM…)."""
        name = path.rsplit(SEP, 1)[-1].lower()
        if name not in self.rules.cands:
            return False
        r = self.rules.match_path(path, hidden=True)
        return r is not None and r.id != own_rule.id and (r.act in ("review", "keep") or r.id == "not_a_cache")

    def _empty(self, job, target, rule):
        """Delete what is inside one folder. Never follows links, never leaves the folder.

        With `keep_days` (temp folders) each top-level item is one unit: if anything
        inside it changed recently, a running program may still be using it, so the
        whole item is left exactly as it is.
        """
        root = target["path"]
        keep_after = time.time() - rule.keep_days * 86400 if rule.keep_days else None
        wroot = extended(root)
        stack = [(wroot, root, False)]
        while stack:
            wpath, shown, leaving = stack.pop()
            if leaving:
                if wpath != wroot and self._rmdir(wpath):       # only succeeds when it is empty
                    job["dirs"] += 1
                continue
            if self._cancel:
                return
            job["current"] = shown
            stack.append((wpath, shown, True))
            top = wpath == wroot
            try:
                entries = list(os.scandir(wpath))
            except OSError:
                job["skipped"] += 1
                target["skipped"] += 1
                continue
            for e in entries:
                if self._cancel:
                    return
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    job["skipped"] += 1
                    target["skipped"] += 1
                    continue
                attrs = getattr(st, "st_file_attributes", 0)
                is_dir = stat.S_ISDIR(st.st_mode) or bool(attrs & _ATTR_DIRECTORY)
                recent = keep_after is not None and st.st_mtime > keep_after
                if stat.S_ISLNK(st.st_mode) or attrs & _ATTR_REPARSE:
                    # a link: remove the link itself, never what it points to
                    if recent:
                        job["kept"] += 1
                    elif not self._unlink_link(e.path, is_dir and IS_WIN):
                        job["skipped"] += 1
                        target["skipped"] += 1
                    continue
                if is_dir:
                    sub = shown + SEP + e.name
                    if self._protected(sub, rule):
                        job["protected"] += 1
                    elif keep_after is not None and top and (recent or self._touched_since(e.path, keep_after)):
                        job["kept"] += 1
                    else:
                        stack.append((e.path, sub, False))
                    continue
                if recent:
                    job["kept"] += 1
                    continue
                if self._unlink(e.path, attrs):
                    job["files"] += 1
                    job["freed"] += st.st_size
                    target["freed"] += st.st_size
                else:
                    job["skipped"] += 1
                    target["skipped"] += 1

    @staticmethod
    def _touched_since(path, cutoff):
        """True when anything inside `path` was changed after `cutoff` (or cannot be read)."""
        stack = [path]
        while stack:
            try:
                entries = list(os.scandir(stack.pop()))
            except OSError:
                return True
            for e in entries:
                try:
                    st = e.stat(follow_symlinks=False)
                except OSError:
                    return True
                if st.st_mtime > cutoff:
                    return True
                attrs = getattr(st, "st_file_attributes", 0)
                if stat.S_ISDIR(st.st_mode) and not attrs & _ATTR_REPARSE:
                    stack.append(e.path)
        return False

    @staticmethod
    def _unlink(path, attrs):
        try:
            os.unlink(path)
            return True
        except FileNotFoundError:
            return True                                         # someone else removed it first
        except PermissionError:
            # Read-only caches (Go modules) need the flag cleared first. A file that is
            # really in use fails again here — and is left alone.
            try:
                if IS_WIN:
                    if not attrs & _ATTR_READONLY:
                        return False
                    os.chmod(path, stat.S_IWRITE)
                else:
                    parent = os.path.dirname(path)
                    os.chmod(parent, os.stat(parent).st_mode | stat.S_IWUSR | stat.S_IXUSR)
                os.unlink(path)
                return True
            except OSError:
                return False
        except OSError:
            return False

    @staticmethod
    def _unlink_link(path, as_dir):
        try:
            if as_dir:
                os.rmdir(path)                                  # removes a junction / folder link, not its target
            else:
                os.unlink(path)
            return True
        except OSError:
            return False

    @staticmethod
    def _rmdir(path):
        try:
            os.rmdir(path)
            return True
        except PermissionError:
            if IS_WIN:
                return False
            try:                                                # read-only parent folder (Go module cache)
                parent = os.path.dirname(path)
                os.chmod(parent, os.stat(parent).st_mode | stat.S_IWUSR | stat.S_IXUSR)
                os.rmdir(path)
                return True
            except OSError:
                return False
        except OSError:
            return False
