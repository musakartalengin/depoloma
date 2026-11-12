"""Platform glue: volumes, "show in file manager", the app window, WSL, installed programs.

Read-only by design. The only processes started here are a file manager
(to *show* an item), a browser window for the UI, and `wsl.exe … du` (to
measure, never to change, what is inside a Linux distribution).
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import webbrowser

IS_WIN = os.name == "nt"
IS_MAC = sys.platform == "darwin"

if IS_WIN:
    from . import winfs

_NO_WINDOW = 0x08000000 if IS_WIN else 0


def home():
    return os.path.expanduser("~")


def data_dir():
    """Where Depoloma keeps its own small files (the clean-up log). Never a cache folder it would offer."""
    if IS_WIN:
        return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.join(home(), "AppData", "Local"), "Depoloma")
    if IS_MAC:
        return os.path.join(home(), "Library", "Logs", "Depoloma")
    state = os.environ.get("XDG_STATE_HOME") or os.path.join(home(), ".local", "state")
    return os.path.join(state, "depoloma")


def is_elevated():
    if IS_WIN:
        return winfs.is_elevated()
    try:
        return os.geteuid() == 0
    except AttributeError:
        return False


def prepare_privileges():
    if IS_WIN and winfs.is_elevated():
        winfs.enable_backup_privilege()


# ── volumes ──────────────────────────────────────────────────────────────────

def _usage(path):
    """Total / used / free. On Linux, ext4 keeps ~5 % in reserve for root: that is neither
    "used" nor "free" for a normal user, so `used` is taken as reported, not as total − free."""
    try:
        u = shutil.disk_usage(path)
        return {"total": u.total, "free": u.free, "used": u.used}
    except OSError:
        return None


def volumes():
    """Drives / filesystems the user can scan: [{path, total, free, used, fs, label, kind}]."""
    out = []
    if IS_WIN:
        sysdrive = (os.environ.get("SystemDrive") or "C:").upper() + "\\"
        for root, kind in winfs.drives():
            u = _usage(root)
            if not u or not u["total"]:
                continue
            info = winfs.volume_info(root)
            v = {"path": root, "kind": kind, "fs": info["fs"], "label": info["label"],
                 "system": root.upper() == sysdrive}
            v.update(u)
            if info["fs"].upper() == "NTFS":
                v["mft"] = winfs.ntfs_mft_bytes(root) or 0
            out.append(v)
    elif IS_MAC:
        data = "/System/Volumes/Data"
        root = data if os.path.isdir(data) else "/"
        u = _usage(root)
        if u:
            v = {"path": root, "kind": "fixed", "fs": "APFS", "label": "Macintosh HD", "system": True}
            v.update(u)
            out.append(v)
        try:
            for name in sorted(os.listdir("/Volumes")):
                p = os.path.join("/Volumes", name)
                if os.path.ismount(p):
                    u = _usage(p)
                    if u and u["total"]:
                        v = {"path": p, "kind": "removable", "fs": "", "label": name, "system": False}
                        v.update(u)
                        out.append(v)
        except OSError:
            pass
    else:
        try:
            with open("/proc/mounts", "r", encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            text = ""
        seen = set()
        for mnt, fs in linux_mounts(text):
            try:
                dev = os.stat(mnt).st_dev          # the same filesystem mounted twice is listed once
            except OSError:
                continue
            if dev in seen:
                continue
            seen.add(dev)
            u = _usage(mnt)
            if u and u["total"]:
                v = {"path": mnt, "kind": "fixed" if not mnt.startswith(("/media/", "/mnt/", "/run/media/")) else "removable",
                     "fs": fs, "label": "", "system": mnt == "/"}
                v.update(u)
                out.append(v)
        if not out:
            u = _usage("/")
            if u:
                v = {"path": "/", "kind": "fixed", "fs": "", "label": "", "system": True}
                v.update(u)
                out.append(v)
    return out


_REAL_FS = {"ext2", "ext3", "ext4", "btrfs", "xfs", "zfs", "f2fs", "ntfs", "ntfs3", "fuseblk", "vfat", "exfat",
            "reiserfs", "jfs", "bcachefs"}
_SKIP_MOUNTS = ("/snap/", "/var/lib/docker", "/var/lib/containers", "/boot", "/run/", "/proc", "/sys", "/dev",
                "/var/snap/")


def linux_mounts(text):
    """(mount point, filesystem) of the real, user-relevant filesystems in /proc/mounts text.
    Always starts with "/" so there is something to scan even in a container."""
    out = [("/", "")]
    for line in text.splitlines():
        m = line.split()
        if len(m) < 3:
            continue
        mnt, fs = m[1].replace("\\040", " "), m[2]
        if mnt == "/":
            out[0] = ("/", fs)
        elif fs in _REAL_FS and (mnt, fs) not in out and (
                mnt.startswith("/run/media/") or not mnt.startswith(_SKIP_MOUNTS)):
            out.append((mnt, fs))
    return out


# ── showing things to the user ───────────────────────────────────────────────

def reveal(path):
    """Open the file manager with `path` selected. Shows, never modifies."""
    if not os.path.lexists(path):
        return False
    try:
        if IS_WIN:
            subprocess.Popen('explorer /select,"%s"' % path.replace('"', ""))
        elif IS_MAC:
            subprocess.Popen(["open", "-R", path])
        else:
            quiet = {"stdout": subprocess.DEVNULL, "stderr": subprocess.DEVNULL}
            if shutil.which("dbus-send"):
                # Nautilus, Nemo, Dolphin…: opens the folder with the item selected
                from urllib.parse import quote
                rc = subprocess.call(
                    ["dbus-send", "--session", "--print-reply", "--dest=org.freedesktop.FileManager1",
                     "--type=method_call", "/org/freedesktop/FileManager1",
                     "org.freedesktop.FileManager1.ShowItems",
                     "array:string:file://" + quote(os.path.abspath(path)), "string:"], timeout=8, **quiet)
                if rc == 0:
                    return True
            subprocess.Popen(["xdg-open", path if os.path.isdir(path) else os.path.dirname(path)], **quiet)
        return True
    except (OSError, subprocess.SubprocessError):
        return False


def _app_browsers():
    """Chromium-family browsers that can show the UI as a chrome-less app window."""
    if IS_WIN:
        pf = os.environ.get("ProgramFiles", r"C:\Program Files")
        pf86 = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
        local = os.environ.get("LOCALAPPDATA", "")
        return [
            os.path.join(pf86, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(pf, r"Microsoft\Edge\Application\msedge.exe"),
            os.path.join(pf, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pf86, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(local, r"Google\Chrome\Application\chrome.exe"),
            os.path.join(pf, r"BraveSoftware\Brave-Browser\Application\brave.exe"),
        ]
    if IS_MAC:
        return [
            "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
            "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
            "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser",
            "/Applications/Chromium.app/Contents/MacOS/Chromium",
        ]
    names = ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser", "microsoft-edge", "brave-browser")
    return [p for p in (shutil.which(n) for n in names) if p]


def open_ui(url, mode="app"):
    """Show the UI. 'app' = own window without browser chrome (falls back to a tab),
    'tab' = default browser, 'none' = just print the address."""
    if mode == "none":
        return "none"
    if not IS_WIN and not IS_MAC and not (os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY")):
        return "none"                      # a server or SSH session: nothing to open a window on
    if mode == "app":
        for exe in _app_browsers():
            if exe and os.path.isfile(exe):
                try:
                    subprocess.Popen([exe, "--app=" + url, "--window-size=1380,900", "--new-window"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=_NO_WINDOW)
                    return "app"
                except OSError:
                    continue
    try:
        webbrowser.open(url)
        return "tab"
    except Exception:
        return "none"


# ── WSL ──────────────────────────────────────────────────────────────────────

def _decode(raw):
    if b"\x00" in raw:
        return raw.decode("utf-16-le", "replace")
    return raw.decode("utf-8", "replace")


def wsl_list():
    """Registered WSL distributions with the size of their virtual disk."""
    if not IS_WIN:
        return []
    try:
        distros = winfs.wsl_distros()
    except Exception:
        return []
    running = set()
    if distros and shutil.which("wsl.exe"):
        try:
            p = subprocess.run(["wsl.exe", "-l", "--running", "-q"], capture_output=True, timeout=15,
                               creationflags=_NO_WINDOW)
            if p.returncode == 0:
                running = {line.strip() for line in _decode(p.stdout).splitlines() if line.strip()}
        except (OSError, subprocess.SubprocessError):
            pass
    for d in distros:
        d["running"] = d["name"] in running
        d["internal"] = d["name"].startswith("docker-desktop")
    return distros


_WSL_SCRIPT = "df -kP / 2>/dev/null | tail -n 1; echo @@DU@@; du -xk -d 5 / 2>/dev/null"


def wsl_scan(name, timeout=1800):
    """Measure folder sizes *inside* a WSL distribution with `du` (read-only).

    Starts the distribution if it is not running. Returns
    {used, total, tree} where tree is a nested {name, path, size, children}.
    """
    if not IS_WIN or not shutil.which("wsl.exe"):
        raise RuntimeError("WSL is not available")
    cmd = ["wsl.exe", "-d", name, "-u", "root", "--", "sh", "-c", _WSL_SCRIPT]
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=_NO_WINDOW)
    text = p.stdout.decode("utf-8", "replace")
    if "@@DU@@" not in text:
        raise RuntimeError((_decode(p.stderr) or _decode(p.stdout) or "wsl failed").strip()[:400])
    head, body = text.split("@@DU@@", 1)
    used = total = 0
    cols = head.split()
    if len(cols) >= 4:
        try:
            total, used = int(cols[-5]) * 1024, int(cols[-4]) * 1024
        except (ValueError, IndexError):
            pass
    return {"used": used, "total": total, "tree": du_tree(body)}


def du_tree(text, min_bytes=1 << 20):
    """Parse `du -k` output into a nested tree, dropping entries below `min_bytes`."""
    sizes = {}
    for line in text.splitlines():
        kb, sep, path = line.partition("\t")
        if not sep:
            continue
        try:
            sizes[path] = int(kb) * 1024
        except ValueError:
            continue
    root = {"name": "/", "path": "/", "size": sizes.get("/", 0), "children": []}
    index = {"/": root}
    for path in sorted(sizes, key=lambda p: p.count("/")):
        if path == "/" or sizes[path] < min_bytes:
            continue
        parent_path = path.rsplit("/", 1)[0] or "/"
        parent = index.get(parent_path)
        if parent is None:
            continue
        node = {"name": path.rsplit("/", 1)[1], "path": path, "size": sizes[path], "children": []}
        parent["children"].append(node)
        index[path] = node
    stack = [root]
    while stack:
        n = stack.pop()
        n["children"].sort(key=lambda c: -c["size"])
        stack.extend(n["children"])
    return root


# ── which program does a folder belong to? (to warn "you used this recently") ─

_VENDOR_DIRS = {"google", "microsoft", "mozilla", "bravesoftware", "opera software", "jetbrains", "adobe", "nvidia",
                "nvidia corporation", "amd", "yandex", "apple", "apple computer", "intel", "unity"}


def app_of(path, home):
    """(label, folder) of the program a folder inside the user profile belongs to, or None.

    …\\AppData\\Roaming\\Claude\\Cache          → ("Claude", …\\AppData\\Roaming\\Claude)
    …\\AppData\\Local\\Google\\Chrome\\…\\Cache  → ("Chrome", …\\AppData\\Local\\Google\\Chrome)
    ~/.config/Code/Cache                        → ("Code", ~/.config/Code)
    ~/.gradle/caches                            → (".gradle", ~/.gradle)
    """
    home = home.rstrip("\\/")
    if not os.path.normcase(path).startswith(os.path.normcase(home) + os.sep):
        return None
    parts = [p for p in path[len(home):].replace("\\", "/").split("/") if p]
    low = [p.lower() for p in parts]
    if not parts:
        return None
    if low[0] == "appdata" and len(parts) > 2:
        i = 2                                             # AppData/<Local|Roaming|LocalLow>/<app>
    elif low[0] in (".config", ".cache", "snap") and len(parts) > 1:
        i = 1
    elif len(parts) > 2 and (low[0], low[1]) in ((".var", "app"), (".local", "share"), ("library", "caches"),
                                                 ("library", "application support")):
        i = 2
    else:
        i = 0                                             # ~/.gradle, ~/.npm, ~/go …
    j = i
    if low[i] == "packages" and i + 1 < len(parts):      # Store apps: Packages/<Name_publisherid>
        j = i + 1
        label = parts[j].split("_")[0]
    else:
        if low[i] in _VENDOR_DIRS and i + 1 < len(parts):
            j = i + 1                                     # Google/Chrome, Microsoft/Edge …
        label = parts[j]
    return label, os.path.join(home, *parts[:j + 1])


# ── running programs (only to warn before a clean-up) ───────────────────────

_APP_ALIASES = {"edge": "msedge", "brave-browser": "brave", "opera software": "opera", "telegram desktop": "telegram",
                "teams": "ms-teams", "msteams": "ms-teams", "yandexbrowser": "browser"}
_NOT_APPS = ("system", "windows", "users", "explorer", "local", "roaming", "temp", "cache", "data", "default")


def running_process_names():
    """Lower-case names of running programs, without extension (best effort, never raises)."""
    names = set()
    try:
        if IS_WIN:
            p = subprocess.run(["tasklist", "/FO", "CSV", "/NH"], capture_output=True, timeout=15, creationflags=_NO_WINDOW)
            for line in p.stdout.decode("mbcs", "replace").splitlines():
                name = line.split('","', 1)[0].strip().strip('"').lower()
                if name.endswith(".exe"):
                    name = name[:-4]
                if name:
                    names.add(name)
        else:
            p = subprocess.run(["ps", "-A", "-o", "comm="], capture_output=True, timeout=15)
            for line in p.stdout.decode("utf-8", "replace").splitlines():
                name = os.path.basename(line.strip()).lower()
                if name:
                    names.add(name)
    except (OSError, subprocess.SubprocessError):
        pass
    return names


def running_apps(paths):
    """Which of the given cache folders seem to belong to a program that is open right now?

    Matches a folder name on the path against running program names, e.g.
    …\\Google\\Chrome\\User Data\\Default\\Cache → chrome.exe is running → "Chrome".
    """
    running = running_process_names()
    if not running:
        return []
    found = []
    for path in paths:
        for part in path.replace("\\", "/").split("/"):
            low = part.lower().split("_")[0]                    # MSTeams_8wekyb3d8bbwe → msteams
            if not low or low in _NOT_APPS:
                continue
            if low in running or _APP_ALIASES.get(low) in running:
                label = part.split("_")[0] if "_" in part and len(part) > 20 else part
                if label not in found:
                    found.append(label)
                break
    return found[:12]


# ── installed programs ───────────────────────────────────────────────────────

def installed_programs():
    """Installed programs with the space they take: the Windows uninstall list, or
    apt / snap / flatpak packages on Linux."""
    try:
        if IS_WIN:
            return winfs.installed_programs()
        if IS_MAC:
            return []
        return linux_packages()
    except Exception:
        return []


def parse_dpkg(text):
    """Rows of `dpkg-query -W -f='${Package}\\t${Version}\\t${Installed-Size}\\t${db:Status-Abbrev}\\n'`."""
    out = []
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 4 or not parts[3].startswith("ii"):      # only fully installed packages
            continue
        try:
            kb = int(parts[2] or 0)
        except ValueError:
            kb = 0
        out.append({"name": parts[0], "version": parts[1], "publisher": "apt", "location": "",
                    "estimated": kb * 1024, "installed": ""})
    return out


def parse_flatpak(text):
    """Rows of `flatpak list --app --columns=name,application,version,size` (tab separated)."""
    units = {"b": 1, "kb": 1000, "mb": 1000 ** 2, "gb": 1000 ** 3, "tb": 1000 ** 4,
             "bytes": 1, "kib": 1024, "mib": 1024 ** 2, "gib": 1024 ** 3}
    out = []
    for line in text.splitlines():
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 4 or not parts[1]:
            continue
        size = 0
        bits = parts[3].replace(" ", " ").replace(",", ".").split()
        if len(bits) == 2:
            try:
                size = int(float(bits[0]) * units.get(bits[1].lower(), 0))
            except ValueError:
                size = 0
        out.append({"name": parts[0] or parts[1], "version": parts[2], "publisher": "flatpak", "location": "",
                    "estimated": size, "installed": ""})
    return out


def snap_packages(folder="/var/lib/snapd/snaps"):
    """Snap packages by the size of their files on disk; every kept revision counts."""
    sizes = {}
    try:
        entries = list(os.scandir(folder))
    except OSError:
        return []
    for e in entries:
        if not e.name.endswith(".snap"):
            continue
        name = e.name[:-5].rsplit("_", 1)[0]
        try:
            size = e.stat().st_size
        except OSError:
            continue
        s = sizes.setdefault(name, [0, 0])
        s[0] += size
        s[1] += 1
    return [{"name": name, "version": "×%d" % n if n > 1 else "", "publisher": "snap", "location": folder,
             "estimated": size, "installed": "", "exact": True} for name, (size, n) in sizes.items()]


def linux_packages(limit=500):
    env = dict(os.environ, LC_ALL="C")
    out = []
    if shutil.which("dpkg-query"):
        try:
            p = subprocess.run(["dpkg-query", "-W", "-f=${Package}\t${Version}\t${Installed-Size}\t${db:Status-Abbrev}\n"],
                               capture_output=True, timeout=30, env=env)
            out += parse_dpkg(p.stdout.decode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError):
            pass
    out += snap_packages()
    if shutil.which("flatpak"):
        try:
            p = subprocess.run(["flatpak", "list", "--app", "--columns=name,application,version,size"],
                               capture_output=True, timeout=30, env=env)
            out += parse_flatpak(p.stdout.decode("utf-8", "replace"))
        except (OSError, subprocess.SubprocessError):
            pass
    out.sort(key=lambda a: -a["estimated"])
    return out[:limit]


def relaunch_elevated(argv):
    """Restart as administrator (Windows asks the user through UAC)."""
    if not IS_WIN:
        return False
    if getattr(sys, "frozen", False):
        return winfs.relaunch_elevated(argv)
    pkg_parent = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return winfs.relaunch_elevated(["-m", "depoloma"] + list(argv), cwd=pkg_parent)


def system_lang():
    """'tr' on a Turkish system, otherwise 'en'."""
    try:
        if IS_WIN:
            import ctypes
            return "tr" if ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == 0x1F else "en"
        lang = os.environ.get("LC_ALL") or os.environ.get("LC_MESSAGES") or os.environ.get("LANG") or ""
        return "tr" if lang.lower().startswith("tr") else "en"
    except Exception:
        return "en"
