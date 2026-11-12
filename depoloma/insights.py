"""Turns a finished scan into the findings the UI shows.

One pass over the kept tree produces:
  * the "where does the space go" category split
  * findings per known folder kind (caches, node_modules, games, WSL …)
  * forgotten projects, stale downloads, big old files
  * the largest files and the main hotspots
Everything is derived from the in-memory tree — the disk is not touched again.
"""
from __future__ import annotations

import os
import time

from . import rules as _rules
from .scanner import (AGE_DAYS, F_DENIED, F_LINK, F_MOUNT, F_PARTIAL, F_PROJECT, F_PRUNED, F_REGEN,
                      project_kinds)

MB = 1 << 20
GB = 1 << 30
DAY = 86400

STALE_PROJECT_DAYS = 180
OLD_DOWNLOAD_DAYS = 90
OLD_FILE_DAYS = 365
MAX_ITEMS = 60
MAX_CLEAN_ITEMS = 400       # cleanable findings list (nearly) everything, so "select all" means all

# file kinds that only count as findings among personal files
_PERSONAL_FILE_RULES = ("archive", "installer", "video", "disk_image", "db_backup")
_CHILD_RULES = ("program", "game", "store_app", "mac_app", "home")


def node_brief(node):
    rule = node.rule
    return {"id": node.id, "name": node.name, "path": node.path(), "size": node.size,
            "newest": node.newest, "files": node.nfiles,
            "rule": rule.id if rule is not None and not rule.hidden else None}


def build_summary(scanner, volumes, can_clean=None, last_used=None):
    """`can_clean(node, path)` tells which listed folders Depoloma may offer to empty;
    `last_used(path, newest)` → (program, timestamp) says when their program was last used."""
    rs = scanner.rules
    now = time.time()
    totals = scanner.rule_totals
    cats = dict.fromkeys(_rules.CATS, 0)
    rule_nodes = {}              # rule id → [node]
    rule_minus = {}              # rule id → bytes that belong to a nested, different finding
    file_groups = {}             # file rule id → [(size, name, node, mtime)]
    bigfiles = []
    projects = []
    old_downloads = []
    old_big = []
    file_rule = rs.file_rule

    node_minus = {}              # node id → the same, per listed folder
    stack = []
    for i, root in enumerate(scanner.root_nodes):
        near = scanner.root_near[i] if i < len(scanner.root_near) else None
        stack.append((root, (near.cat if near is not None and near.cat else "other"), None, None, 0))

    while stack:
        node, cat, anchor, near_id, ctx = stack.pop()      # ctx bits: 1 = in a project, 2 = in Downloads
        rule = node.rule
        flags = node.flags
        if flags & F_PROJECT:
            cat = "dev"
            ctx |= 1
            projects.append(node)
        if rule is not None:
            if rule.cat:
                cat = rule.cat
            if not rule.hidden:
                near_id = rule.id
                if rule.cat:
                    rule_nodes.setdefault(rule.id, []).append(node)
                if rule.reclaim:
                    anchor = node
                elif anchor is not None and rule.act in ("review", "keep"):
                    # e.g. AI models inside ~/.cache: not "safe to clear" like the rest
                    rid = anchor.rule.id
                    rule_minus[rid] = rule_minus.get(rid, 0) + node.size
                    node_minus[anchor.id] = node_minus.get(anchor.id, 0) + node.size
                    anchor = None
        is_downloads = rule is not None and rule.id == "downloads"
        if is_downloads:
            ctx |= 2
        kids = node.children
        own = node.size
        if kids:
            for c in kids:
                own -= c.size
                stack.append((c, cat, anchor, near_id, ctx))
        files = node.files
        if files:
            for name, size, mtime in files:
                if mtime < 347155200:                      # before 1981: a placeholder date, not a real one
                    mtime = 0
                fr = file_rule(name)
                fcat = cat
                frid = None
                if fr is not None:
                    fid = fr["id"]
                    if fr["cat"] in ("system", "virtual"):
                        fcat = fr["cat"]
                        if cat != "virtual":               # inside WSL / emulator folders it is already a finding
                            frid = fid
                    elif anchor is not None:
                        pass                               # inside a cache folder that is already a finding
                    elif fid in _PERSONAL_FILE_RULES:
                        if cat == "personal" and not ctx & 1:
                            frid = fid
                    elif fid == "ai_model":
                        if near_id != "ai_models" and cat in ("personal", "dev", "other"):
                            frid = fid
                    else:
                        frid = fid
                    if frid is not None and fid not in _PERSONAL_FILE_RULES:
                        file_groups.setdefault(fid, []).append((size, name, node, mtime))
                if fcat != cat:
                    own -= size
                    cats[fcat] += size
                if size >= 20 * MB:
                    bigfiles.append((size, name, node, mtime, fcat, frid))
                    if (frid in _PERSONAL_FILE_RULES and size >= 100 * MB and mtime and now - mtime > OLD_FILE_DAYS * DAY
                            and not ctx & 2):
                        old_big.append((size, name, node, mtime, frid))
                if is_downloads and mtime and now - mtime > OLD_DOWNLOAD_DAYS * DAY:
                    old_downloads.append({"t": "f", "id": node.id, "name": name, "path": _fpath(node, name),
                                          "size": size, "newest": mtime,
                                          "rule": ("file:" + fr["id"]) if fr is not None else None})
            if is_downloads and kids:
                for c in kids:
                    if c.size >= MB and c.newest and now - c.newest > OLD_DOWNLOAD_DAYS * DAY:
                        b = node_brief(c)
                        b["t"] = "d"
                        old_downloads.append(b)
        elif kids and rule is not None and rule.id == "downloads":
            for c in kids:
                if c.size >= MB and c.newest and now - c.newest > OLD_DOWNLOAD_DAYS * DAY:
                    b = node_brief(c)
                    b["t"] = "d"
                    old_downloads.append(b)
        if own > 0:
            cats[cat] += own

    findings = []

    # ── findings from folder rules ──────────────────────────────────────────
    for rid, rule in rs.rules.items():
        if rule.hidden or rule.nofind or not rule.cat or rid in _CHILD_RULES:
            continue
        tot = totals.get(rid)
        if not tot or not tot[1]:
            continue
        size = max(0, tot[1] - rule_minus.get(rid, 0))
        floor = rule.min or (50 * MB if rule.act in ("safe", "regen", "review") else 500 * MB)
        if size < floor:
            continue
        nodes = rule_nodes.get(rid, [])
        if rule.child is not None:                       # a container: list what is inside it
            items = []
            for n in nodes:
                for c in n.children or ():
                    if c.size >= MB:
                        items.append(c)
            count = len(items)
        else:
            items = nodes
            count = tot[0]
        cleanable = rule.clean and rule.child is None and can_clean is not None
        items = sorted(items, key=lambda n: -n.size)[:MAX_CLEAN_ITEMS if cleanable else MAX_ITEMS]
        briefs = []
        for n in items:
            b = node_brief(n)
            b["size"] = max(0, n.size - node_minus.get(n.id, 0))
            if b["size"] >= MB or not briefs:
                if cleanable:
                    b["clean"] = bool(can_clean(n, b["path"]))
                    if last_used is not None:
                        b["app"], b["used"] = last_used(b["path"], n.newest)
                briefs.append(b)
        briefs.sort(key=lambda b: -b["size"])
        if rule.child is None:
            count = max(len(briefs), count if rule.reclaim else len(briefs))
        findings.append({"id": rid, "kind": "rule", "cat": rule.cat, "act": rule.act, "size": size, "count": count,
                         "items": briefs, "clean": any(b.get("clean") for b in briefs)})

    # ── findings from notable files ─────────────────────────────────────────
    for fid, lst in file_groups.items():
        fr = rs.file_rules[fid]
        lst.sort(key=lambda t: -t[0])
        size = sum(t[0] for t in lst)
        if size < 50 * MB:
            continue
        findings.append({"id": "file:" + fid, "kind": "file", "cat": fr["cat"], "act": fr["act"], "size": size,
                         "count": len(lst), "items": [_file_brief(t, "file:" + fid) for t in lst[:MAX_ITEMS]]})

    # ── forgotten projects ──────────────────────────────────────────────────
    plist = []
    stale = []
    for n in projects:
        if n.size < MB:
            continue
        mask, regen = n.proj
        last = n.newest_src or n.newest
        age = int((now - last) / DAY) if last else -1
        item = {"id": n.id, "name": n.name, "path": n.path(), "size": n.size, "regen": min(regen, n.size),
                "newest": last, "days": age, "kinds": project_kinds(mask), "files": n.nfiles}
        plist.append(item)
        if age >= STALE_PROJECT_DAYS and n.size >= 20 * MB:
            stale.append(item)
    plist.sort(key=lambda p: -p["size"])
    stale.sort(key=lambda p: -p["size"])
    if stale:
        findings.append({"id": "stale_projects", "kind": "special", "cat": "dev", "act": "review",
                         "size": sum(p["size"] for p in stale), "count": len(stale), "items": stale[:MAX_ITEMS],
                         "regen": sum(p["regen"] for p in stale)})

    # ── stale downloads / big old personal files ────────────────────────────
    if old_downloads:
        old_downloads.sort(key=lambda d: -d["size"])
        size = sum(d["size"] for d in old_downloads)
        if size >= 50 * MB:
            findings.append({"id": "old_downloads", "kind": "special", "cat": "personal", "act": "review",
                             "size": size, "count": len(old_downloads), "items": old_downloads[:MAX_ITEMS]})
    if old_big:
        old_big.sort(key=lambda t: -t[0])
        findings.append({"id": "old_big_files", "kind": "special", "cat": "personal", "act": "review",
                         "size": sum(t[0] for t in old_big), "count": len(old_big),
                         "items": [_file_brief(t, "file:" + t[4]) for t in old_big[:MAX_ITEMS]]})

    order = {"safe": 0, "regen": 1, "review": 2, "keep": 3, "info": 4}
    findings.sort(key=lambda f: (order.get(f["act"], 9), -f["size"]))
    reclaim = {"safe": sum(f["size"] for f in findings if f["act"] == "safe"),
               "regen": sum(f["size"] for f in findings if f["act"] == "regen"),
               "review": sum(f["size"] for f in findings if f["act"] == "review" and f["kind"] != "rule")}

    # ── largest files ───────────────────────────────────────────────────────
    bigfiles.sort(key=lambda t: -t[0])
    big = []
    for size, name, node, mtime, fcat, frid in bigfiles[:400]:
        i = name.rfind(".")
        ext = name[i + 1:].lower() if i > 0 else ""
        big.append({"name": name, "path": _fpath(node, name), "dir": node.id, "size": size, "mtime": mtime,
                    "cat": fcat, "group": _rules.ext_group(ext), "rule": ("file:" + frid) if frid else None})

    # ── file types ──────────────────────────────────────────────────────────
    groups = {}
    for ext, (n, b) in scanner.exts.items():
        g = groups.setdefault(_rules.ext_group(ext), {"count": 0, "size": 0, "exts": []})
        g["count"] += n
        g["size"] += b
        g["exts"].append((b, n, ext))
    types = []
    for key, g in groups.items():
        g["exts"].sort(reverse=True)
        types.append({"key": key, "count": g["count"], "size": g["size"],
                      "exts": [{"ext": e, "size": b, "count": n} for b, n, e in g["exts"][:6]]})
    types.sort(key=lambda t: -t["size"])

    # ── volumes: scanned vs. really used ────────────────────────────────────
    vols = []
    scanned_total = 0
    for root in scanner.root_nodes:
        scanned_total += root.size
        v = {"path": root.name, "id": root.id, "scanned": root.size, "files": root.nfiles, "dirs": root.ndirs,
             "cloud": root.cloud, "linked": root.linked, "isVolume": False}
        for vol in volumes:
            if os.path.normcase(vol["path"]) == os.path.normcase(root.name):
                v.update({"isVolume": True, "total": vol["total"], "free": vol["free"], "used": vol["used"],
                          "fs": vol.get("fs", ""), "label": vol.get("label", "")})
                mft = vol.get("mft") or 0
                if not mft and vol.get("fs", "").upper() == "NTFS":
                    mft = (root.nfiles + root.ndirs) * 1024           # ~1 KB per file record
                v["meta"] = mft
                v["hidden"] = max(0, vol["used"] - root.size - mft)
                break
        vols.append(v)

    hidden = sum(v.get("hidden", 0) for v in vols)
    meta = sum(v.get("meta", 0) for v in vols)
    cats["system"] += meta

    return {
        "generated": now,
        "elapsed": round(scanner.finished - scanner.started, 1),
        "state": scanner.state,
        "files": sum(r.nfiles for r in scanner.root_nodes),
        "dirs": sum(r.ndirs for r in scanner.root_nodes),
        "scanned": scanned_total,
        "volumes": vols,
        "cats": [{"key": k, "size": cats[k]} for k in _rules.CATS],
        "hidden": hidden,
        "meta": meta,
        "findings": findings,
        "reclaim": reclaim,
        "projects": plist[:400],
        "bigfiles": big,
        "types": types,
        "ages": [{"key": k, "size": b} for k, b in zip(_age_keys(), scanner.ages)],
        "hotspots": _hotspots(scanner, file_rule),
        "denied": {"count": scanner.ndenied, "paths": scanner.denied[:150]},
    }


def _age_keys():
    keys = ["lt%d" % AGE_DAYS[0]]
    for a, b in zip(AGE_DAYS, AGE_DAYS[1:]):
        keys.append("%d-%d" % (a, b))
    keys.append("gt%d" % AGE_DAYS[-1])
    return keys


def _fpath(node, name):
    p = node.path()
    return p + name if p.endswith(os.sep) else p + os.sep + name


def _file_brief(t, rule=None):
    size, name, node, mtime = t[0], t[1], t[2], t[3]
    return {"t": "f", "id": node.id, "name": name, "path": _fpath(node, name), "size": size, "newest": mtime,
            "rule": rule}


def _hotspots(scanner, file_rule, limit=10):
    """The handful of places where the space really sits.

    Walks down from each root and stops at folders that are a meaningful unit:
    a known kind (games, WSL, a cache), a project, or a folder without one
    dominant child.
    """
    total = sum(r.size for r in scanner.root_nodes) or 1
    floor = max(total // 100, 256 * MB)
    out = []
    stack = list(scanner.root_nodes)
    while stack:
        node = stack.pop()
        for name, size, mtime in node.files or ():
            if size >= floor:
                fr = file_rule(name)
                out.append({"t": "f", "id": node.id, "name": name, "path": _fpath(node, name), "size": size,
                            "newest": mtime, "rule": ("file:" + fr["id"]) if fr else None})
        for c in node.children or ():
            if c.size < floor:
                continue
            rule = c.rule
            unit = (c.flags & F_PROJECT) or (rule is not None and not rule.hidden and rule.child is None
                                              and rule.id != "program"
                                              and (rule.reclaim or rule.act == "review"))
            if not unit and c.children:
                top = max(k.size for k in c.children)
                bigfile = max((f[1] for f in c.files), default=0) if c.files else 0
                if top >= c.size * 0.6 or bigfile >= c.size * 0.6 or c.size > total * 0.12 or (
                        rule is not None and (rule.child is not None or rule.act in ("info", "keep"))
                        and top >= floor):
                    stack.append(c)
                    continue
            b = node_brief(c)
            b["t"] = "d"
            b["rule"] = rule.id if rule is not None and not rule.hidden else None
            b["project"] = bool(c.flags & F_PROJECT)
            out.append(b)
    out.sort(key=lambda h: -h["size"])
    return out[:limit]


def node_json(scanner, node, deep=False, limit=400):
    """A folder and its direct contents, largest first, for the explorer view."""
    rs = scanner.rules
    crumbs = []
    n = node
    while n is not None:
        crumbs.append({"id": n.id, "name": n.name})
        n = n.parent
    crumbs.reverse()
    items = []
    floor = node.size * 0.05
    for c in node.children or ():
        items.append(_child_json(c, rs, deep, floor))
    for name, size, mtime in node.files or ():
        fr = rs.file_rule(name)
        items.append({"t": "f", "name": name, "size": size, "newest": mtime,
                      "rule": ("file:" + fr["id"]) if fr else None})
    items.sort(key=lambda x: -x["size"])
    more = None
    if len(items) > limit:
        rest = items[limit:]
        items = items[:limit]
        more = {"n": len(rest), "size": sum(x["size"] for x in rest)}
    out = _child_json(node, rs, False)
    out.update({"path": node.path(), "crumbs": crumbs, "items": items, "more": more,
                "small": {"n": node.small_n, "size": node.small_b},
                "tiny": {"n": node.tiny_n, "size": node.tiny_b},
                "dirs": node.ndirs, "cloud": node.cloud, "linked": node.linked})
    return out


def _subs(c, levels, floor):
    """Largest contents of a folder for the map; big sub-folders are expanded a few levels."""
    sub = []
    for k in c.children or ():
        if k.size:
            e = {"t": "d", "id": k.id, "name": k.name, "size": k.size, "open": bool(k.children or k.files)}
            if levels > 1 and k.size >= floor and e["open"]:
                e["sub"] = _subs(k, levels - 1, floor)
            sub.append(e)
    for name, size, _m in c.files or ():
        sub.append({"t": "f", "name": name, "size": size})
    sub.sort(key=lambda x: -x["size"])
    return sub[:14]


def _child_json(c, rs, deep, floor=0):
    flags = c.flags
    d = {"t": "d", "id": c.id, "name": c.name, "size": c.size, "files": c.nfiles, "newest": c.newest,
         "rule": c.rule.id if c.rule is not None and not c.rule.hidden else None,
         "open": bool(c.children or c.files),
         "denied": bool(flags & F_DENIED), "partial": bool(flags & F_PARTIAL),
         "link": bool(flags & (F_LINK | F_MOUNT)), "regen": bool(flags & F_REGEN)}
    if flags & F_PROJECT and c.proj:
        d["project"] = {"kinds": project_kinds(c.proj[0]), "regen": min(c.proj[1], c.size),
                        "newest": c.newest_src or c.newest}
    if deep:
        d["sub"] = _subs(c, 4, floor)
    return d
