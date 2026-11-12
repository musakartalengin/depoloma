"""Depoloma scan engine — strictly read-only.

Walks one or more roots with a small pool of threads and builds a compact
in-memory size tree:

* every folder that matters becomes a `Node`; folders too small to care about
  are folded into their parent so memory stays bounded on multi-million-file disks
* sizes are bytes actually allocated on disk (cloud placeholders count as 0,
  hard-linked files are counted once where that matters)
* known folders are labelled by `rules.RuleSet`, projects are detected by their
  marker files (package.json, .git, Cargo.toml …)

Nothing in here opens a file for writing, moves, renames or deletes anything.
"""
from __future__ import annotations

import os
import stat as _stat
import sys
import threading
import time
from collections import deque

from . import rules as _rules

IS_WIN = os.name == "nt"
SEP = os.sep

if IS_WIN:
    from . import winfs

K_FILE, K_DIR, K_LINK, K_MOUNT = 0, 1, 2, 3

BIG_FILE = 1 << 20          # files ≥ 1 MiB are remembered individually
TINY_DIR = 256 << 10        # deep folders smaller than this are folded into their parent
SHALLOW = 4                 # …but the first levels are always kept complete
MAX_DENIED = 400

# node flags
F_DENIED = 1                # could not be listed (permissions)
F_LINK = 2                  # junction / symlink — not followed
F_MOUNT = 4                 # another filesystem — not crossed
F_PROJECT = 8               # looks like a software project
F_REGEN = 16                # rebuildable content (node_modules, venv …)
F_PRUNED = 32               # children were folded away (tiny folder)
F_KEEP = 64                 # internal: part of it was scanned by another thread
F_PARTIAL = 128             # listed only partially (e.g. WindowsApps without admin)

# zone bits inherited down the tree
Z_NOPROJ = 1                # don't look for projects here
Z_REGEN = 2                 # inside rebuildable content
Z_INPROJ = 4                # inside a detected project
Z_DEDUPE = 8                # count hard-linked files once
Z_HOMECHILD = 16            # direct child of a user profile
Z_RECLAIM = 32              # inside a cache / rebuildable folder already counted
Z_SERIAL = 64               # one thread walks this subtree in a fixed order (hard-link ownership)
Z_GUARD = 128               # inside a guarded folder (keep rule, installed programs, AI tool): no name-based cache rule

# project kinds (bit flags → names)
P_KINDS = ("git", "node", "python", "rust", "go", "java", "dotnet", "flutter", "php", "ruby", "cpp",
           "unity", "unreal", "swift", "docker")
_P = {name: 1 << i for i, name in enumerate(P_KINDS)}
_U1, _U2 = 1 << 20, 1 << 21          # Unity needs both Assets/ and ProjectSettings/
MARK_FILES = {
    ".git": _P["git"], "package.json": _P["node"], "pyproject.toml": _P["python"], "requirements.txt": _P["python"],
    "setup.py": _P["python"], "Pipfile": _P["python"], "environment.yml": _P["python"], "manage.py": _P["python"],
    "Cargo.toml": _P["rust"], "go.mod": _P["go"], "pom.xml": _P["java"], "build.gradle": _P["java"],
    "build.gradle.kts": _P["java"], "settings.gradle": _P["java"], "pubspec.yaml": _P["flutter"],
    "composer.json": _P["php"], "Gemfile": _P["ruby"], "CMakeLists.txt": _P["cpp"], "Makefile": _P["cpp"],
    "platformio.ini": _P["cpp"], "Package.swift": _P["swift"], "docker-compose.yml": _P["docker"],
    "docker-compose.yaml": _P["docker"], "compose.yaml": _P["docker"],
}
MARK_EXTS = {"sln": _P["dotnet"], "csproj": _P["dotnet"], "fsproj": _P["dotnet"], "vbproj": _P["dotnet"],
             "vcxproj": _P["cpp"], "uproject": _P["unreal"]}
MARK_DIRS = {".git": _P["git"], ".svn": _P["git"], ".hg": _P["git"], "Assets": _U1, "ProjectSettings": _U2}

AGE_DAYS = (30, 180, 365, 730, 1825)     # bucket edges for the "how old is my data" chart


def project_kinds(mask):
    return [name for i, name in enumerate(P_KINDS) if mask & (1 << i)]


class Node(object):
    __slots__ = ("name", "parent", "children", "files", "size", "nfiles", "ndirs", "small_n", "small_b",
                 "tiny_n", "tiny_b", "newest", "newest_src", "cloud", "linked", "flags", "rule", "proj", "id")

    def __init__(self, name, parent):
        self.name = name
        self.parent = parent
        self.children = None      # list[Node] of kept sub-folders
        self.files = None         # list[(name, bytes, mtime)] of files ≥ BIG_FILE
        self.size = 0             # bytes on disk, whole subtree
        self.nfiles = 0           # files in the whole subtree
        self.ndirs = 0            # folders in the whole subtree
        self.small_n = 0          # direct files < BIG_FILE …
        self.small_b = 0          # … and their bytes
        self.tiny_n = 0           # direct sub-folders folded away …
        self.tiny_b = 0           # … and their bytes
        self.newest = 0           # latest modification time in the subtree
        self.newest_src = 0       # same, ignoring rebuildable folders
        self.cloud = 0            # bytes that live only in the cloud (not on disk)
        self.linked = 0           # bytes not counted because another hard link was counted
        self.flags = 0
        self.rule = None
        self.proj = None          # [kind mask, rebuildable bytes] for project roots
        self.id = -1

    def path(self):
        parts = []
        n = self
        while n.parent is not None:
            parts.append(n.name)
            n = n.parent
        root = n.name
        if not parts:
            return root
        parts.reverse()
        return (root if root.endswith(SEP) else root + SEP) + SEP.join(parts)


def _join(parent, name):
    return parent + name if parent.endswith(SEP) else parent + SEP + name


def list_dir_generic(path, root_dev):
    """Portable listing via os.scandir (POSIX, and the Windows fallback)."""
    out = []
    add = out.append
    with os.scandir(path) as it:
        for e in it:
            try:
                st = e.stat(follow_symlinks=False)
            except OSError:
                continue
            mode = st.st_mode
            if IS_WIN:
                attrs = st.st_file_attributes
                if attrs & 0x10:
                    if attrs & 0x400 and getattr(st, "st_reparse_tag", 0) & 0x20000000:
                        add((e.name, K_LINK, 0, 0, 0, 0))
                    else:
                        add((e.name, K_DIR, 0, 0, 0, 0))
                    continue
                size = st.st_size
                if attrs & 0x401000:                       # online-only cloud placeholder
                    add((e.name, K_FILE, 0, int(st.st_mtime), size, 0))
                else:                                       # estimate allocation: round up to a 4K cluster
                    add((e.name, K_FILE, (size + 4095) & ~4095 if size > 700 else 0, int(st.st_mtime), 0, 0))
            elif _stat.S_ISDIR(mode):
                # a folder's own blocks count too (as `du` does); another filesystem is not crossed
                add((e.name, K_DIR if st.st_dev == root_dev else K_MOUNT, st.st_blocks * 512, 0, 0, 0))
            elif _stat.S_ISLNK(mode) or not _stat.S_ISREG(mode):
                add((e.name, K_FILE, 0, int(st.st_mtime), 0, 0))
            else:
                alloc = st.st_blocks * 512
                cloud = 0
                if alloc == 0 and getattr(st, "st_flags", 0) & 0x40000000:   # macOS dataless (iCloud) file
                    cloud = st.st_size
                add((e.name, K_FILE, alloc, int(st.st_mtime), cloud, st.st_ino if st.st_nlink > 1 else 0))
    return out


class _Worker(object):
    """Per-thread state, merged into the scanner when the scan ends."""

    def __init__(self):
        self.exts = {}
        self.ages = [0] * (len(AGE_DAYS) + 1)
        self.rtot = {}
        self.denied = []
        self.ndenied = 0
        self.counts = [0, 0, 0]              # files, folders, bytes — read live for progress
        self.lister = winfs.DirLister() if IS_WIN else None
        self.generic = not IS_WIN


class Scanner(object):
    def __init__(self, roots, ruleset=None, threads=None, inherit_context=True):
        self.roots = [self._norm_root(r) for r in roots]
        self.rules = ruleset or _rules.RuleSet(home=os.path.expanduser("~"))
        # A root below a known folder (say, inside AppData) is judged in that
        # context. Turn off to treat the root as a neutral starting point.
        self.inherit_context = inherit_context
        self.threads = threads or max(2, min(8, os.cpu_count() or 4))
        self.state = "idle"                  # idle → scanning → done | cancelled | error
        self.error = ""
        self.started = 0.0
        self.finished = 0.0
        self.current = ""
        self.root_nodes = []
        self.root_near = []                  # nearest known folder above each root (context)
        self.nodes = []                      # id → Node (after the scan)
        self.exts = {}                       # ext → [count, bytes]
        self.ages = [0] * (len(AGE_DAYS) + 1)
        self.rule_totals = {}                # rule id → [folders, bytes]
        self.denied = []
        self.ndenied = 0
        self._workers = []
        self._cancel = False
        self._cv = threading.Condition()
        self._queue = deque()
        self._active = 0
        self._waiting = 0
        self._lock = threading.Lock()
        self._seen = set()
        self._tails = []
        self._salt = 0
        self._dev = 0
        now = time.time()
        self._now = int(now) + 86400
        self._cuts = tuple(int(now - d * 86400) for d in AGE_DAYS)
        self._appx = None

    # ── public ────────────────────────────────────────────────────────────

    @staticmethod
    def _norm_root(path):
        path = os.path.abspath(path)
        if IS_WIN and len(path) == 2 and path[1] == ":":
            path += SEP
        return path

    def cancel(self):
        self._cancel = True
        with self._cv:
            self._cv.notify_all()

    def progress(self):
        files = dirs = size = 0
        for w in self._workers:
            c = w.counts
            files += c[0]
            dirs += c[1]
            size += c[2]
        end = self.finished or time.time()
        return {"state": self.state, "files": files, "dirs": dirs, "bytes": size, "current": self.current,
                "elapsed": round(end - self.started, 1) if self.started else 0, "error": self.error}

    def run(self):
        self.state = "scanning"
        self.started = time.time()
        try:
            self._workers = [_Worker() for _ in range(self.threads)]
            for i, root in enumerate(self.roots):
                if self._cancel:
                    break
                self._scan_root(root, i)
            self._merge()
            self._index()
            self.state = "cancelled" if self._cancel else "done"
        except Exception as exc:                       # pragma: no cover - defensive
            self.error = "%s: %s" % (type(exc).__name__, exc)
            self.state = "error"
            raise
        finally:
            self._seen = set()
            self.finished = time.time()
        return self

    def find(self, path):
        """Node for a path inside a scanned root, or None if it was folded away."""
        norm = os.path.normcase(os.path.abspath(path))
        for root in self.root_nodes:
            base = os.path.normcase(root.name)
            if norm == base or norm == base.rstrip(SEP):
                return root
            prefix = base if base.endswith(SEP) else base + SEP
            if not norm.startswith(prefix):
                continue
            node = root
            for part in norm[len(prefix):].split(SEP):
                if not part:
                    continue
                nxt = None
                for c in node.children or ():
                    if os.path.normcase(c.name) == part:
                        nxt = c
                        break
                if nxt is None:
                    return None
                node = nxt
            return node
        return None

    # ── one root ──────────────────────────────────────────────────────────

    def _scan_root(self, root_path, index):
        root = Node(root_path, None)
        self.root_nodes.append(root)
        self._salt = index << 64
        self._tails = []
        zone, near, crule = self._context_above(root_path) if self.inherit_context else (0, None, None)
        self.root_near.append(near)
        if not IS_WIN:
            zone |= Z_DEDUPE
            try:
                self._dev = os.stat(root_path).st_dev
            except OSError:
                self._dev = 0
        self._queue.append((root, root_path, zone, 0, near, crule, None))
        threads = [threading.Thread(target=self._work, args=(w,), name="depoloma-scan", daemon=True)
                   for w in self._workers]
        for t in threads:
            t.start()
        for t in threads:
            t.join()
        self._fixup()

    def _context_above(self, root_path):
        """When the scan starts below a drive root (say, in a user folder), replay
        the rules of the folders above it so the root is understood in context."""
        zone, near, crule = 0, None, None
        norm = root_path.rstrip(SEP)
        parts = norm.split(SEP)
        for k in range(1, len(parts)):
            anc = SEP.join(parts[:k]) or SEP
            lpath = anc.lower().replace("\\", "/").rstrip("/")
            rule = None
            for rx, r in self.rules.cands.get(lpath.rsplit("/", 1)[-1], ()):
                if r is near or r.has is not None or r.inproj or (r.reclaim and zone & Z_RECLAIM):
                    continue
                if r.generic and zone & Z_GUARD:
                    continue
                if rx.search(lpath):
                    rule = r
                    break
            if rule is None:
                rule = crule
            zone &= ~Z_HOMECHILD
            crule = None
            if rule is not None:
                near = rule
                if rule.regen:
                    zone |= Z_REGEN | Z_NOPROJ
                elif rule.np:
                    zone |= Z_NOPROJ
                if rule.reclaim:
                    zone |= Z_RECLAIM | Z_NOPROJ
                if rule.dedupe:
                    zone |= Z_DEDUPE | Z_SERIAL
                if rule.home:
                    zone |= Z_HOMECHILD
                if rule.guards:
                    zone |= Z_GUARD
                crule = rule.child
        return zone, near, crule

    def _work(self, w):
        cv = self._cv
        queue = self._queue
        while True:
            with cv:
                while True:
                    if self._cancel:
                        cv.notify_all()
                        return
                    if queue:
                        task = queue.pop()
                        self._active += 1
                        break
                    if self._active == 0:
                        cv.notify_all()
                        return
                    self._waiting += 1
                    cv.wait(0.5)
                    self._waiting -= 1
            try:
                self._run_task(w, task)
            finally:
                with cv:
                    self._active -= 1
                    if self._active == 0 and not queue:
                        cv.notify_all()

    def _run_task(self, w, task):
        stack = []
        self._enter(w, task, stack)
        while stack:
            fr = stack[-1]
            pend = fr[2]
            if pend and not self._cancel:
                child = pend.pop()
                self._enter(w, (child, _join(fr[1], child.name), fr[3], fr[4] + 1, fr[5], fr[6], fr[7]), stack)
                if self._waiting and len(stack) > 1:
                    self._donate(stack)
            else:
                stack.pop()
                self._leave(w, fr, stack[-1] if stack else None)

    def _donate(self, stack):
        """Hand the shallowest not-yet-scanned sub-folders to idle threads."""
        for i, fr in enumerate(stack):
            if fr[2] and not fr[3] & Z_SERIAL:
                break
        else:
            return
        path, zone, depth, near, crule, proj = fr[1], fr[3], fr[4] + 1, fr[5], fr[6], fr[7]
        tasks = []
        for child in fr[2]:
            child.flags |= F_KEEP
            tasks.append((child, _join(path, child.name), zone, depth, near, crule, proj))
        fr[2] = None
        for j in range(i + 1):                        # their ancestors must survive pruning
            stack[j][0].flags |= F_KEEP
        with self._cv:
            self._queue.extend(tasks)
            self._cv.notify(len(tasks))

    # ── entering a folder: list it, account its files, queue its sub-folders ─

    def _enter(self, w, task, stack):
        node, path, zone, depth, near, crule, proj = task
        self.current = path
        try:
            if w.generic:
                entries = list_dir_generic(path, self._dev)
            else:
                entries = w.lister(path)
        except OSError as exc:
            entries = self._list_failed(w, node, path, exc)

        # which known folder is this?
        lname = node.name.lower() if depth else os.path.basename(path.rstrip(SEP)).lower()
        rule = None
        cands = self.rules.cands.get(lname)
        if cands is not None:
            lpath = path.lower()
            if IS_WIN:
                lpath = lpath.replace("\\", "/")
            lpath = lpath.rstrip("/")
            for rx, r in cands:
                if r is near or (r.reclaim and zone & Z_RECLAIM) or (r.inproj and not zone & Z_INPROJ):
                    continue
                if r.generic and zone & Z_GUARD:
                    continue                           # a "cache" inside a program or an AI tool: hands off
                if rx.search(lpath) is None:
                    continue
                if r.has is not None and not _has(entries, r.has):
                    continue
                if r.generic and _rules.looks_like_data(e[0] for e in entries):
                    continue                           # named like a cache, but holds a profile, a database or code
                rule = r
                break
        if rule is None:
            pcands = self.rules.pcands.get(lname[:_rules.PREFIX_KEY])
            if pcands is not None:                     # names matched by prefix, e.g. Packages/OpenAI.*
                lpath = (path.lower().replace("\\", "/") if IS_WIN else path.lower()).rstrip("/")
                for stem, rx, r in pcands:
                    if lname.startswith(stem) and r is not near and rx.search(lpath) is not None \
                            and not (r.reclaim and zone & Z_RECLAIM):
                        rule = r
                        break
        if rule is None and crule is not None and not (crule.reclaim and zone & Z_RECLAIM):
            rule = crule
        homechild = zone & Z_HOMECHILD
        zone &= ~Z_HOMECHILD
        child_rule = None
        if rule is not None:
            node.rule = rule
            near = rule
            if rule.regen:
                zone |= Z_REGEN | Z_NOPROJ
                node.flags |= F_REGEN
            elif rule.np:
                zone |= Z_NOPROJ
            if rule.reclaim:
                zone |= Z_RECLAIM | Z_NOPROJ
            if rule.dedupe:
                zone |= Z_DEDUPE | Z_SERIAL
            if rule.home:
                zone |= Z_HOMECHILD
            if rule.guards:
                zone |= Z_GUARD
            child_rule = rule.child
        elif homechild and lname[:1] == ".":
            zone |= Z_NOPROJ                           # ~/.something → tool data, not a project

        size = node.size                       # the folder's own blocks (POSIX), set by its parent's listing
        nfiles = newest = cloud = linked = small_n = small_b = marks = 0
        files = None
        children = None
        pending = None
        detect = rule is None and depth > 0 and not zone & (Z_NOPROJ | Z_INPROJ)
        dedupe = zone & Z_DEDUPE
        exts = w.exts
        ages = w.ages
        t1, t2, t3, t4, t5 = self._cuts
        now = self._now
        for name, kind, alloc, mt, cl, fid in entries:
            if kind == 0:
                if dedupe and fid:
                    fid += self._salt
                    with self._lock:
                        seen = self._seen
                        n0 = len(seen)
                        seen.add(fid)
                        dup = len(seen) == n0
                    if dup:
                        linked += alloc
                        alloc = 0
                nfiles += 1
                size += alloc
                if newest < mt < now:
                    newest = mt
                if cl:
                    cloud += cl
                i = name.rfind(".")
                ext = name[i + 1:].lower() if 0 < i and len(name) - i < 13 else ""
                e = exts.get(ext)
                if e is None:
                    exts[ext] = [1, alloc]
                else:
                    e[0] += 1
                    e[1] += alloc
                if mt >= t2:
                    ages[0 if mt >= t1 else 1] += alloc
                elif mt >= t4:
                    ages[2 if mt >= t3 else 3] += alloc
                else:
                    ages[4 if mt >= t5 else 5] += alloc
                if alloc >= BIG_FILE:
                    if files is None:
                        files = []
                    files.append((name, alloc, mt))
                else:
                    small_n += 1
                    small_b += alloc
                if detect:
                    m = MARK_FILES.get(name) or MARK_EXTS.get(ext)
                    if m:
                        marks |= m
            else:
                child = Node(name, node)
                if kind == 1:
                    child.size = alloc         # counted when the folder itself is walked
                if children is None:
                    children = []
                children.append(child)
                if kind == 1:
                    if pending is None:
                        pending = []
                    pending.append(child)
                    if detect:
                        m = MARK_DIRS.get(name)
                        if m:
                            marks |= m
                else:
                    child.flags = F_LINK if kind == 2 else F_MOUNT

        node.size = size
        node.nfiles = nfiles
        node.newest = node.newest_src = newest
        node.cloud = cloud
        node.linked = linked
        node.small_n = small_n
        node.small_b = small_b
        node.files = files
        node.children = children
        if marks:
            if marks & _U1 and marks & _U2:
                marks |= _P["unity"]
            marks &= ~(_U1 | _U2)
            if marks:
                node.proj = [marks, 0]
                node.flags |= F_PROJECT
                zone |= Z_INPROJ
                proj = node
        if pending is not None and rule is not None and rule.id == "windows":
            # WinSxS goes last so System32 & co. "own" the hard-linked files and
            # WinSxS shows only what it costs on top.
            for k, c in enumerate(pending):
                if c.name.lower() == "winsxs":
                    pending.insert(0, pending.pop(k))
                    break
        c = w.counts
        c[0] += nfiles
        c[1] += 1
        c[2] += size
        stack.append([node, path, pending, zone, depth, near, child_rule, proj])

    def _list_failed(self, w, node, path, exc):
        code = exc.args[0] if exc.args else 0
        if IS_WIN and not w.generic and code in winfs.ERR_UNSUPPORTED:
            w.generic = True                              # exotic filesystem: use the portable lister
            try:
                return list_dir_generic(path, self._dev)
            except OSError:
                pass
        if (IS_WIN and code in winfs.ERR_GONE) or (not IS_WIN and code == 2):
            return []                                     # vanished while we were scanning
        node.flags |= F_DENIED
        w.ndenied += 1
        if len(w.denied) < MAX_DENIED:
            w.denied.append(path)
        if IS_WIN and path.lower().endswith("\\program files\\windowsapps"):
            # Not listable without admin, but each package folder is readable.
            if self._appx is None:
                try:
                    self._appx = winfs.appx_package_dirs()
                except Exception:
                    self._appx = []
            prefix = path.lower() + "\\"
            names = [p[len(prefix):] for p in self._appx if p.lower().startswith(prefix) and "\\" not in p[len(prefix):]]
            if names:
                node.flags |= F_PARTIAL
                return [(n, K_DIR, 0, 0, 0, 0) for n in names]
        return []

    # ── leaving a folder: roll its totals up and fold away what is tiny ─────

    def _leave(self, w, fr, parent_fr):
        node = fr[0]
        size = node.size
        rule = node.rule
        flags = node.flags
        if rule is not None:
            t = w.rtot.get(rule.id)
            if t is None:
                w.rtot[rule.id] = [1, size]
            else:
                t[0] += 1
                t[1] += size
            if flags & F_REGEN and fr[7] is not None:
                with self._lock:
                    fr[7].proj[1] += size
        if parent_fr is None:
            if node.parent is not None:                    # scanned as a separate task → merged in _fixup
                self._tails.append((node, size, node.nfiles, node.ndirs + 1, node.cloud, node.linked,
                                    node.newest, node.newest_src))
        else:
            p = parent_fr[0]
            p.size += size
            p.nfiles += node.nfiles
            p.ndirs += node.ndirs + 1
            p.cloud += node.cloud
            p.linked += node.linked
            if node.newest > p.newest:
                p.newest = node.newest
            if not flags & F_REGEN and node.newest_src > p.newest_src:
                p.newest_src = node.newest_src
        ch = node.children
        if ch is None:
            return
        depth = fr[4]
        if size < TINY_DIR and depth >= SHALLOW and not flags & F_KEEP:
            node.children = None
            node.flags = flags | F_PRUNED
        elif depth >= SHALLOW - 1 or len(ch) > 400:
            keep = []
            tn = tb = 0
            for c in ch:
                if c.size >= TINY_DIR or c.flags & (F_KEEP | F_DENIED):
                    keep.append(c)
                else:
                    tn += 1
                    tb += c.size
            if tn:
                node.children = keep or None
                node.tiny_n = tn
                node.tiny_b = tb

    def _fixup(self):
        """Add the totals of sub-trees that other threads scanned to all their ancestors."""
        totals = {}
        for node, size, nfiles, ndirs, cloud, linked, newest, src in self._tails:
            src_ok = not node.flags & F_REGEN
            in_regen = False
            credited = False
            a = node.parent
            while a is not None:
                a.size += size
                a.nfiles += nfiles
                a.ndirs += ndirs
                a.cloud += cloud
                a.linked += linked
                if newest > a.newest:
                    a.newest = newest
                if src_ok and src > a.newest_src:
                    a.newest_src = src
                if a.flags & F_REGEN:
                    in_regen = True
                    src_ok = False
                if a.rule is not None:
                    totals[a.rule.id] = totals.get(a.rule.id, 0) + size
                if in_regen and not credited and a.flags & F_PROJECT:
                    a.proj[1] += size
                    credited = True
                a = a.parent
        # Hand-offs were protected from folding while in flight; fold the tiny ones now.
        for item in self._tails:
            node = item[0]
            p = node.parent
            if p is None or node.size >= TINY_DIR or node.flags & F_DENIED or not p.children:
                continue
            depth = 0
            a = p
            while a.parent is not None:
                a = a.parent
                depth += 1
            if depth >= SHALLOW - 1:
                try:
                    p.children.remove(node)
                except ValueError:
                    continue
                p.tiny_n += 1
                p.tiny_b += node.size
                if not p.children:
                    p.children = None
        self._tails = []
        for rid, extra in totals.items():
            t = self.rule_totals.get(rid)
            if t is None:
                self.rule_totals[rid] = [0, extra]
            else:
                t[1] += extra

    def _merge(self):
        for w in self._workers:
            for ext, (n, b) in w.exts.items():
                e = self.exts.get(ext)
                if e is None:
                    self.exts[ext] = [n, b]
                else:
                    e[0] += n
                    e[1] += b
            for i, b in enumerate(w.ages):
                self.ages[i] += b
            for rid, (n, b) in w.rtot.items():
                t = self.rule_totals.get(rid)
                if t is None:
                    self.rule_totals[rid] = [n, b]
                else:
                    t[0] += n
                    t[1] += b
            self.denied.extend(w.denied)
            self.ndenied += w.ndenied
        self.denied = sorted(set(self.denied))[:MAX_DENIED]

    def _index(self):
        nodes = self.nodes = []
        stack = list(reversed(self.root_nodes))
        while stack:
            n = stack.pop()
            n.id = len(nodes)
            nodes.append(n)
            if n.children:
                stack.extend(n.children)


def _has(entries, wanted):
    lw = wanted.lower()
    for e in entries:
        if e[0].lower() == lw:
            return True
    return False
