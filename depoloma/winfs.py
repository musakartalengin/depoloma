"""Windows-only helpers built on ctypes + winreg.

Everything in this module only *reads* (directory listings, volume facts,
registry values). Nothing here writes, moves or deletes anything.
"""
from __future__ import annotations

import ctypes
import os
import struct
import sys
from ctypes import wintypes

K_FILE, K_DIR, K_LINK, K_MOUNT = 0, 1, 2, 3

_k32 = ctypes.WinDLL("kernel32", use_last_error=True)

_k32.CreateFileW.argtypes = [wintypes.LPCWSTR, wintypes.DWORD, wintypes.DWORD, wintypes.LPVOID,
                             wintypes.DWORD, wintypes.DWORD, wintypes.HANDLE]
_k32.CreateFileW.restype = wintypes.HANDLE
_k32.GetFileInformationByHandleEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.LPVOID, wintypes.DWORD]
_k32.GetFileInformationByHandleEx.restype = wintypes.BOOL
_k32.CloseHandle.argtypes = [wintypes.HANDLE]
_k32.CloseHandle.restype = wintypes.BOOL
_k32.GetLogicalDriveStringsW.argtypes = [wintypes.DWORD, wintypes.LPWSTR]
_k32.GetLogicalDriveStringsW.restype = wintypes.DWORD
_k32.GetDriveTypeW.argtypes = [wintypes.LPCWSTR]
_k32.GetDriveTypeW.restype = wintypes.UINT
_k32.GetVolumeInformationW.argtypes = [wintypes.LPCWSTR, wintypes.LPWSTR, wintypes.DWORD,
                                       ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                       ctypes.POINTER(wintypes.DWORD), wintypes.LPWSTR, wintypes.DWORD]
_k32.GetVolumeInformationW.restype = wintypes.BOOL
_k32.GetDiskFreeSpaceW.argtypes = [wintypes.LPCWSTR, ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD),
                                   ctypes.POINTER(wintypes.DWORD), ctypes.POINTER(wintypes.DWORD)]
_k32.GetDiskFreeSpaceW.restype = wintypes.BOOL
_k32.DeviceIoControl.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPVOID, wintypes.DWORD,
                                 wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(wintypes.DWORD), wintypes.LPVOID]
_k32.DeviceIoControl.restype = wintypes.BOOL

_INVALID = wintypes.HANDLE(-1).value
_FILE_LIST_DIRECTORY = 0x0001
_SHARE_ALL = 0x7
_OPEN_EXISTING = 3
_BACKUP_SEMANTICS = 0x02000000          # required to open a directory handle
_FILE_ID_BOTH_DIRECTORY_INFO = 10

_ATTR_DIRECTORY = 0x10
_ATTR_REPARSE = 0x400
_ATTR_CLOUD = 0x400000 | 0x1000         # RECALL_ON_DATA_ACCESS | OFFLINE  → online-only placeholder
_TAG_NAME_SURROGATE = 0x20000000        # junctions / symlinks: "this name points somewhere else"
_FT_EPOCH = 116444736000000000          # 1601 → 1970 in 100 ns ticks

# FILE_ID_BOTH_DIR_INFO: NextEntryOffset, FileIndex, Creation, LastAccess, LastWrite, Change,
# EndOfFile, AllocationSize, FileAttributes, FileNameLength, EaSize/ReparseTag, (short name), FileId
_ENTRY = struct.Struct("<IIqqqqqqIII28xq")
_NAME_OFFSET = 104

ERR_ACCESS = (5, 32, 1920, 1314)        # denied, sharing violation, can't access, privilege not held
ERR_GONE = (2, 3, 21, 1005, 123)        # vanished / not ready / unrecognised volume / bad name
ERR_UNSUPPORTED = (1, 50, 87)           # filesystem can't do this info class → caller falls back


def extended(path):
    r"""`\\?\`-prefixed form, so paths longer than 260 chars still open."""
    if path.startswith("\\\\?\\"):
        return path
    if path.startswith("\\\\"):
        return "\\\\?\\UNC\\" + path[2:]
    return "\\\\?\\" + path


class DirLister:
    """List one directory in as few syscalls as possible.

    `GetFileInformationByHandleEx(FileIdBothDirectoryInfo)` hands back hundreds of
    entries per call, each with the *allocated* size (true bytes on disk — correct
    for compressed, sparse and cloud-placeholder files) and a file id (lets us
    count hard-linked files once). Returns tuples
    `(name, kind, bytes_on_disk, mtime, cloud_only_bytes, file_id)`.
    """

    def __init__(self, bufsize=1 << 16):
        self._size = bufsize
        self._buf = bytearray(bufsize)
        self._cbuf = (ctypes.c_char * bufsize).from_buffer(self._buf)

    def __call__(self, path):
        h = _k32.CreateFileW(extended(path), _FILE_LIST_DIRECTORY, _SHARE_ALL, None,
                             _OPEN_EXISTING, _BACKUP_SEMANTICS, None)
        if h == _INVALID:
            raise OSError(ctypes.get_last_error(), "cannot open directory", path)
        out = []
        add = out.append
        buf = self._buf
        cbuf = self._cbuf
        size = self._size
        unpack = _ENTRY.unpack_from
        query = _k32.GetFileInformationByHandleEx
        try:
            while True:
                if not query(h, _FILE_ID_BOTH_DIRECTORY_INFO, cbuf, size):
                    err = ctypes.get_last_error()
                    if err == 18 or (err == 2 and not out):      # no more files / empty root
                        break
                    if out:                                      # keep what we already read
                        break
                    raise OSError(err, "cannot list directory", path)
                off = 0
                while True:
                    nxt, _i, _c, _a, mt, _ch, eof, alloc, attrs, nlen, tag, fid = unpack(buf, off)
                    base = off + _NAME_OFFSET
                    name = buf[base:base + nlen].decode("utf-16-le", "replace")
                    if attrs & _ATTR_DIRECTORY:
                        if name != "." and name != "..":
                            if attrs & _ATTR_REPARSE and tag & _TAG_NAME_SURROGATE:
                                add((name, K_LINK, 0, 0, 0, 0))
                            else:
                                add((name, K_DIR, 0, 0, 0, 0))
                    else:
                        cloud = eof - alloc if (attrs & _ATTR_CLOUD and eof > alloc) else 0
                        add((name, K_FILE, alloc, (mt - _FT_EPOCH) // 10000000, cloud, fid))
                    if not nxt:
                        break
                    off += nxt
        finally:
            _k32.CloseHandle(h)
        return out


# ── volumes ──────────────────────────────────────────────────────────────────

def drives():
    """Fixed and removable drive roots, e.g. ['C:\\', 'D:\\']."""
    n = _k32.GetLogicalDriveStringsW(0, None)
    buf = ctypes.create_unicode_buffer(n + 1)
    _k32.GetLogicalDriveStringsW(n, buf)
    out = []
    for root in buf[:n].split("\0"):
        if not root:
            continue
        kind = _k32.GetDriveTypeW(root)
        if kind in (2, 3):                                  # removable, fixed
            out.append((root, "fixed" if kind == 3 else "removable"))
    return out


def volume_info(root):
    """{'fs': 'NTFS', 'label': '...', 'cluster': 4096} for a drive root (best effort)."""
    info = {"fs": "", "label": "", "cluster": 4096}
    label = ctypes.create_unicode_buffer(261)
    fs = ctypes.create_unicode_buffer(261)
    if _k32.GetVolumeInformationW(root, label, 261, None, None, None, fs, 261):
        info["fs"] = fs.value
        info["label"] = label.value
    spc, bps, fc, tc = wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD(), wintypes.DWORD()
    if _k32.GetDiskFreeSpaceW(root, ctypes.byref(spc), ctypes.byref(bps), ctypes.byref(fc), ctypes.byref(tc)):
        info["cluster"] = spc.value * bps.value or 4096
    return info


def ntfs_mft_bytes(root):
    """Exact size of the NTFS master file table, or None when Windows won't tell us.

    The MFT (the filesystem's own index: ~1 KB per file and folder) is real disk
    usage that no folder scan can see, so we ask the volume for it.
    """
    drive = root.rstrip("\\")
    for path, access, flags in (("\\\\.\\" + drive, 0, 0), ("\\\\?\\" + drive + "\\", 0, _BACKUP_SEMANTICS)):
        h = _k32.CreateFileW(path, access, _SHARE_ALL, None, _OPEN_EXISTING, flags, None)
        if h == _INVALID:
            continue
        try:
            out = ctypes.create_string_buffer(128)
            got = wintypes.DWORD(0)
            # FSCTL_GET_NTFS_VOLUME_DATA
            if _k32.DeviceIoControl(h, 0x00090064, None, 0, out, 128, ctypes.byref(got), None):
                return struct.unpack_from("<q", out.raw, 56)[0]
        finally:
            _k32.CloseHandle(h)
    return None


# ── privileges ───────────────────────────────────────────────────────────────

def is_elevated():
    try:
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except Exception:
        return False


def enable_backup_privilege():
    """When running as administrator, switch on SeBackupPrivilege so protected
    folders (System Volume Information, other users' profiles…) can be *listed*.
    It grants read access for backup-style traversal only. No-op when not elevated.
    """
    try:
        adv = ctypes.WinDLL("advapi32", use_last_error=True)

        class LUID(ctypes.Structure):
            _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]

        class TOKEN_PRIVILEGES(ctypes.Structure):
            _fields_ = [("PrivilegeCount", wintypes.DWORD), ("Luid", LUID), ("Attributes", wintypes.DWORD)]

        adv.OpenProcessToken.argtypes = [wintypes.HANDLE, wintypes.DWORD, ctypes.POINTER(wintypes.HANDLE)]
        adv.LookupPrivilegeValueW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR, ctypes.POINTER(LUID)]
        adv.AdjustTokenPrivileges.argtypes = [wintypes.HANDLE, wintypes.BOOL, ctypes.POINTER(TOKEN_PRIVILEGES),
                                              wintypes.DWORD, wintypes.LPVOID, wintypes.LPVOID]
        _k32.GetCurrentProcess.restype = wintypes.HANDLE
        token = wintypes.HANDLE()
        if not adv.OpenProcessToken(_k32.GetCurrentProcess(), 0x0020 | 0x0008, ctypes.byref(token)):
            return False
        try:
            tp = TOKEN_PRIVILEGES()
            tp.PrivilegeCount = 1
            tp.Attributes = 0x2                              # SE_PRIVILEGE_ENABLED
            if not adv.LookupPrivilegeValueW(None, "SeBackupPrivilege", ctypes.byref(tp.Luid)):
                return False
            adv.AdjustTokenPrivileges(token, False, ctypes.byref(tp), 0, None, None)
            return ctypes.get_last_error() == 0
        finally:
            _k32.CloseHandle(token)
    except Exception:
        return False


def relaunch_elevated(argv, cwd=None):
    """Ask Windows (UAC prompt) to start Depoloma again as administrator."""
    params = " ".join('"%s"' % a.replace('"', '') for a in argv)
    exe = sys.executable
    shell32 = ctypes.windll.shell32
    shell32.ShellExecuteW.argtypes = [wintypes.HWND, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.LPCWSTR,
                                      wintypes.LPCWSTR, ctypes.c_int]
    shell32.ShellExecuteW.restype = wintypes.HINSTANCE
    rc = shell32.ShellExecuteW(None, "runas", exe, params, cwd, 1)
    return (rc or 0) > 32


# ── registry facts ───────────────────────────────────────────────────────────

def _reg_values(key):
    import winreg
    out = {}
    i = 0
    while True:
        try:
            name, value, _t = winreg.EnumValue(key, i)
        except OSError:
            break
        out[name] = value
        i += 1
    return out


def _reg_subkeys(hive, path, view=0):
    import winreg
    try:
        key = winreg.OpenKey(hive, path, 0, winreg.KEY_READ | view)
    except OSError:
        return
    with key:
        i = 0
        while True:
            try:
                sub = winreg.EnumKey(key, i)
            except OSError:
                break
            i += 1
            try:
                with winreg.OpenKey(key, sub) as sk:
                    yield sub, _reg_values(sk)
            except OSError:
                continue


def appx_package_dirs():
    """Install folders of the Store/MSIX apps registered for the current user.

    `C:\\Program Files\\WindowsApps` cannot be listed without admin rights, but each
    package folder inside it is readable — the registry tells us their names.
    """
    import winreg
    out = set()
    path = r"Software\Classes\Local Settings\Software\Microsoft\Windows\CurrentVersion\AppModel\Repository\Packages"
    for _name, vals in _reg_subkeys(winreg.HKEY_CURRENT_USER, path):
        root = vals.get("PackageRootFolder")
        if isinstance(root, str) and root:
            out.add(root.rstrip("\\"))
    return sorted(out)


def wsl_distros():
    """WSL distributions registered for the current user (from the registry)."""
    import winreg
    out = []
    for guid, vals in _reg_subkeys(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Lxss"):
        name = vals.get("DistributionName")
        base = vals.get("BasePath")
        if not isinstance(name, str) or not isinstance(base, str):
            continue
        if base.startswith("\\\\?\\"):
            base = base[4:]
        vhd = os.path.join(base, vals.get("VhdFileName") or "ext4.vhdx")
        size = 0
        try:
            size = os.stat(vhd).st_size
        except OSError:
            vhd = ""
        out.append({"name": name, "guid": guid, "base": base, "vhdx": vhd, "vhdxSize": size,
                    "version": int(vals.get("Version") or 2)})
    return out


def installed_programs():
    """Installed desktop programs as listed under "Apps & features" (registry)."""
    import winreg
    seen = {}
    sources = (
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
        (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
        (winreg.HKEY_CURRENT_USER, 0),
    )
    for hive, view in sources:
        for _sub, v in _reg_subkeys(hive, r"Software\Microsoft\Windows\CurrentVersion\Uninstall", view):
            name = v.get("DisplayName")
            if not isinstance(name, str) or not name.strip():
                continue
            if v.get("SystemComponent") == 1 or v.get("ParentKeyName"):
                continue
            loc = v.get("InstallLocation")
            loc = loc.strip().strip('"').rstrip("\\") if isinstance(loc, str) else ""
            est = v.get("EstimatedSize")
            item = {
                "name": name.strip(),
                "version": str(v.get("DisplayVersion") or ""),
                "publisher": str(v.get("Publisher") or ""),
                "location": loc,
                "estimated": int(est) * 1024 if isinstance(est, int) else 0,
                "installed": str(v.get("InstallDate") or ""),
            }
            key = (item["name"].lower(), item["version"])
            old = seen.get(key)
            if old is None or (not old["location"] and item["location"]):
                seen[key] = item
    return sorted(seen.values(), key=lambda p: p["name"].lower())
