from __future__ import annotations

from pathlib import Path
import ctypes
from ctypes import wintypes
import os
import subprocess
import sys


def enable_autostart(target_path: Path | None = None) -> None:
    link = _startup_link_path()
    link.parent.mkdir(parents=True, exist_ok=True)
    resolved_target, args, work_dir = _resolve_launch_target(target_path)
    _create_shortcut(link, resolved_target, work_dir, args)
    if not link.exists():
        raise RuntimeError(f"shortcut not created: {link}")


def disable_autostart() -> None:
    link = _startup_link_path()
    if not link.exists():
        return
    link.unlink()


def _startup_link_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if appdata:
        return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "NikkeWitchcraftStarter.lnk"
    return (
        Path.home()
        / "AppData"
        / "Roaming"
        / "Microsoft"
        / "Windows"
        / "Start Menu"
        / "Programs"
        / "Startup"
        / "NikkeWitchcraftStarter.lnk"
    )


def _resolve_launch_target(target_path: Path | None) -> tuple[Path, str, Path]:
    if target_path is not None:
        tp = Path(target_path).resolve()
        return tp, "", tp.parent

    if getattr(sys, "frozen", False):
        exe = Path(sys.executable).resolve()
        return exe, "", exe.parent

    script = Path(__file__).resolve().parents[1] / "main.py"
    exe = Path(sys.executable).resolve()
    if exe.name.lower() == "python.exe":
        pyw = exe.with_name("pythonw.exe")
        if pyw.exists():
            exe = pyw
    args = f'"{script}"'
    return exe, args, script.parent


def _create_shortcut(link_path: Path, target_path: Path, work_dir: Path, arguments: str = "") -> None:
    try:
        _create_shortcut_com(link_path, target_path, work_dir, arguments)
    except Exception:
        pass
    if link_path.exists():
        return
    _create_shortcut_powershell(link_path, target_path, work_dir, arguments)


def _create_shortcut_com(link_path: Path, target_path: Path, work_dir: Path, arguments: str = "") -> None:
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    ole32.CoInitialize.argtypes = [ctypes.c_void_p]
    ole32.CoInitialize.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    ole32.CoCreateInstance.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_void_p,
        wintypes.DWORD,
        ctypes.POINTER(GUID),
        ctypes.POINTER(ctypes.c_void_p),
    ]
    ole32.CoCreateInstance.restype = ctypes.c_long

    hr = ole32.CoInitialize(None)
    if hr < 0:
        return
    try:
        psl = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(
            ctypes.byref(CLSID_ShellLink),
            None,
            1,
            ctypes.byref(IID_IShellLinkW),
            ctypes.byref(psl),
        )
        if hr < 0 or not psl:
            raise OSError(f"CoCreateInstance failed: hr={hr}")
        try:
            link = ctypes.cast(psl, ctypes.POINTER(IShellLinkW))
            if link.contents.lpVtbl.contents.SetPath(link, str(target_path)) < 0:
                raise OSError("SetPath failed")
            if link.contents.lpVtbl.contents.SetWorkingDirectory(link, str(work_dir)) < 0:
                raise OSError("SetWorkingDirectory failed")
            if arguments:
                if link.contents.lpVtbl.contents.SetArguments(link, arguments) < 0:
                    raise OSError("SetArguments failed")
            ppf = ctypes.c_void_p()
            hr = link.contents.lpVtbl.contents.QueryInterface(
                link, ctypes.byref(IID_IPersistFile), ctypes.byref(ppf)
            )
            if hr < 0 or not ppf:
                raise OSError(f"QueryInterface(IPersistFile) failed: hr={hr}")
            try:
                pf = ctypes.cast(ppf, ctypes.POINTER(IPersistFile))
                if pf.contents.lpVtbl.contents.Save(pf, str(link_path), True) < 0:
                    raise OSError("IPersistFile.Save failed")
            finally:
                pf.contents.lpVtbl.contents.Release(pf)
        finally:
            link.contents.lpVtbl.contents.Release(link)
    finally:
        ole32.CoUninitialize()


def _create_shortcut_powershell(link_path: Path, target_path: Path, work_dir: Path, arguments: str = "") -> None:
    def esc(text: str) -> str:
        return text.replace("'", "''")

    ps = (
        "$W = New-Object -ComObject WScript.Shell; "
        f"$S = $W.CreateShortcut('{esc(str(link_path))}'); "
        f"$S.TargetPath = '{esc(str(target_path))}'; "
        f"$S.WorkingDirectory = '{esc(str(work_dir))}'; "
        f"$S.Arguments = '{esc(arguments)}'; "
        "$S.Save()"
    )
    subprocess.run(
        ["powershell", "-NoProfile", "-NonInteractive", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass", "-Command", ps],
        check=True,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", wintypes.DWORD),
        ("Data2", wintypes.WORD),
        ("Data3", wintypes.WORD),
        ("Data4", wintypes.BYTE * 8),
    ]


def _guid(s: str) -> GUID:
    import uuid

    u = uuid.UUID(s)
    data4 = (wintypes.BYTE * 8).from_buffer_copy(u.bytes[8:])
    return GUID(u.time_low, u.time_mid, u.time_hi_version, data4)


CLSID_ShellLink = _guid("00021401-0000-0000-C000-000000000046")
IID_IShellLinkW = _guid("000214F9-0000-0000-C000-000000000046")
IID_IPersistFile = _guid("0000010b-0000-0000-C000-000000000046")

class IShellLinkW(ctypes.Structure):
    pass

class IPersistFile(ctypes.Structure):
    pass



class IShellLinkWVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IShellLinkW), ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))),
        ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.POINTER(IShellLinkW))),
        ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.POINTER(IShellLinkW))),
        ("GetPath", ctypes.c_void_p),
        ("GetIDList", ctypes.c_void_p),
        ("SetIDList", ctypes.c_void_p),
        ("GetDescription", ctypes.c_void_p),
        ("SetDescription", ctypes.c_void_p),
        ("GetWorkingDirectory", ctypes.c_void_p),
        ("SetWorkingDirectory", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IShellLinkW), wintypes.LPCWSTR)),
        ("GetArguments", ctypes.c_void_p),
        ("SetArguments", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IShellLinkW), wintypes.LPCWSTR)),
        ("GetHotkey", ctypes.c_void_p),
        ("SetHotkey", ctypes.c_void_p),
        ("GetShowCmd", ctypes.c_void_p),
        ("SetShowCmd", ctypes.c_void_p),
        ("GetIconLocation", ctypes.c_void_p),
        ("SetIconLocation", ctypes.c_void_p),
        ("SetRelativePath", ctypes.c_void_p),
        ("Resolve", ctypes.c_void_p),
        ("SetPath", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IShellLinkW), wintypes.LPCWSTR)),
    ]


class IPersistFileVtbl(ctypes.Structure):
    _fields_ = [
        ("QueryInterface", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IPersistFile), ctypes.POINTER(GUID), ctypes.POINTER(ctypes.c_void_p))),
        ("AddRef", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.POINTER(IPersistFile))),
        ("Release", ctypes.WINFUNCTYPE(ctypes.c_ulong, ctypes.POINTER(IPersistFile))),
        ("GetClassID", ctypes.c_void_p),
        ("IsDirty", ctypes.c_void_p),
        ("Load", ctypes.c_void_p),
        ("Save", ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.POINTER(IPersistFile), wintypes.LPCWSTR, wintypes.BOOL)),
        ("SaveCompleted", ctypes.c_void_p),
        ("GetCurFile", ctypes.c_void_p),
    ]


IShellLinkW._fields_ = [("lpVtbl", ctypes.POINTER(IShellLinkWVtbl))]
IPersistFile._fields_ = [("lpVtbl", ctypes.POINTER(IPersistFileVtbl))]
