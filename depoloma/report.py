"""Plain-text report for terminals and AI coding agents (`depoloma --report`)."""
from __future__ import annotations

import time

_T = {
    "tr": {
        "title": "DEPOLOMA — disk raporu", "disk": "Disk", "used": "dolu", "free": "boş", "of": "/",
        "scanned": "Taranan", "files": "dosya", "dirs": "klasör", "secs": "sn",
        "hidden": "Görünmeyen (korumalı sistem alanı, erişilemeyen klasörler)",
        "cats": "ALAN NEREYE GİDİYOR", "hot": "EN BÜYÜK NOKTALAR", "find": "BULGULAR",
        "safe": "Güvenle temizlenebilir", "regen": "Yeniden üretilebilir", "review": "Gözden geçir",
        "keep": "Dokunma (gerekli)", "info": "Bilgi", "how": "Nasıl", "why": "Not",
        "cat": {"system": "Windows ve sistem", "apps": "Programlar ve oyunlar", "personal": "Kişisel dosyalar",
                "dev": "Geliştirici araçları ve projeler", "data": "Uygulama verileri ve önbellek",
                "virtual": "Sanal diskler (WSL, Docker, emülatör)", "other": "Diğer"},
        "special": {"stale_projects": ("Uzun süredir dokunulmayan projeler", "6 aydan uzun süredir değişmemiş projeler. Hâlâ lazım mı?"),
                    "old_downloads": ("Eski indirmeler", "90 günden eski indirilenler."),
                    "old_big_files": ("Büyük ve eski dosyalar", "1 yıldan eski büyük kişisel dosyalar.")},
        "items": "öğe", "days": "gün önce", "note": "Bu rapor yalnızca bilgi verir; hiçbir şey silinmedi.",
        "reclaim": "Tahmini kazanç",
    },
    "en": {
        "title": "DEPOLOMA — disk report", "disk": "Disk", "used": "used", "free": "free", "of": "of",
        "scanned": "Scanned", "files": "files", "dirs": "folders", "secs": "s",
        "hidden": "Not visible (protected system area, inaccessible folders)",
        "cats": "WHERE THE SPACE GOES", "hot": "BIGGEST HOTSPOTS", "find": "FINDINGS",
        "safe": "Safe to clear", "regen": "Can be regenerated", "review": "Review",
        "keep": "Keep (needed)", "info": "Info", "how": "How", "why": "Note",
        "cat": {"system": "Windows & system", "apps": "Programs & games", "personal": "Personal files",
                "dev": "Developer tools & projects", "data": "App data & caches",
                "virtual": "Virtual disks (WSL, Docker, emulators)", "other": "Other"},
        "special": {"stale_projects": ("Projects untouched for a long time", "Projects unchanged for over 6 months. Still needed?"),
                    "old_downloads": ("Old downloads", "Downloads older than 90 days."),
                    "old_big_files": ("Big old files", "Large personal files older than a year.")},
        "items": "items", "days": "days ago", "note": "This report is information only; nothing was deleted.",
        "reclaim": "Estimated gain",
    },
}


def fmt(n):
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024 or unit == "TB":
            return ("%.0f %s" if unit in ("B", "KB") else "%.1f %s") % (n, unit)
        n /= 1024.0
    return "%.1f TB" % n


_NIX_CATS = {
    "tr": {"system": "Sistem", "virtual": "Sanal diskler (Docker, sanal makineler)"},
    "en": {"system": "System", "virtual": "Virtual disks (Docker, virtual machines)"},
}


def text_report(summary, texts, lang="en", top=12, platform="win"):
    t = dict(_T.get(lang, _T["en"]))
    if platform != "win":                              # "Windows & system" makes no sense on Linux / macOS
        t["cat"] = dict(t["cat"], **_NIX_CATS.get(lang, _NIX_CATS["en"]))
    out = [t["title"], "=" * len(t["title"]), ""]
    for v in summary["volumes"]:
        if v.get("isVolume"):
            out.append("%s %s  %s %s %s %s  ·  %s %s" % (t["disk"], v["path"], fmt(v["used"]), t["of"], fmt(v["total"]),
                                                         t["used"], fmt(v["free"]), t["free"]))
            if v.get("hidden"):
                out.append("  %s: %s" % (t["hidden"], fmt(v["hidden"])))
        else:
            out.append("%s  %s" % (v["path"], fmt(v["scanned"])))
    out.append("%s: %s  ·  %s %s  ·  %s %s  ·  %.0f %s" % (t["scanned"], fmt(summary["scanned"]),
                                                          "{:,}".format(summary["files"]), t["files"],
                                                          "{:,}".format(summary["dirs"]), t["dirs"],
                                                          summary["elapsed"], t["secs"]))
    out += ["", t["cats"], "-" * len(t["cats"])]
    total = sum(c["size"] for c in summary["cats"]) or 1
    for c in sorted(summary["cats"], key=lambda c: -c["size"]):
        if c["size"]:
            out.append("  %10s  %4.1f%%  %s" % (fmt(c["size"]), 100.0 * c["size"] / total, t["cat"].get(c["key"], c["key"])))
    out += ["", t["hot"], "-" * len(t["hot"])]
    for h in summary["hotspots"][:top]:
        label = _title(h.get("rule"), texts, lang)
        out.append("  %10s  %s%s" % (fmt(h["size"]), h["path"], ("   [%s]" % label) if label else ""))
    out += ["", t["find"], "-" * len(t["find"])]
    act = None
    for f in summary["findings"]:
        if f["act"] != act:
            act = f["act"]
            out += ["", "● " + t.get(act, act)]
        if f["kind"] == "special":
            title, what = t["special"].get(f["id"], (f["id"], ""))
            why = how = ""
        else:
            tx = texts.get(f["id"], {}).get(lang) or ("", "", "", "")
            title, what, why, how = tx[0], tx[1], tx[2], tx[3]
        out.append("  %10s  %s  (%d %s)" % (fmt(f["size"]), title, f["count"], t["items"]))
        if what:
            out.append("              %s" % what)
        if why:
            out.append("              %s: %s" % (t["why"], why))
        if how:
            out.append("              %s: %s" % (t["how"], how))
        for item in f["items"][:4]:
            extra = ""
            if item.get("newest"):
                extra = "  (%d %s)" % (max(0, int((time.time() - item["newest"]) / 86400)), t["days"])
            out.append("                · %9s  %s%s" % (fmt(item["size"]), item["path"], extra))
    r = summary["reclaim"]
    out += ["", "%s: %s ≈ %s  ·  %s ≈ %s" % (t["reclaim"], t["safe"], fmt(r["safe"]), t["regen"], fmt(r["regen"])),
            t["note"], ""]
    return "\n".join(out)


def _title(rule_id, texts, lang):
    if not rule_id:
        return ""
    tx = texts.get(rule_id, {}).get(lang)
    return tx[0] if tx else ""
