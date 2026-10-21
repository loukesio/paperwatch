"""Install paperwatch as a background service that starts at login.

* macOS:   a LaunchAgent in ~/Library/LaunchAgents
* Linux:   a systemd --user unit in ~/.config/systemd/user
* Windows: a hidden launcher script in the Startup folder
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

from paperwatch.config import log_path

LABEL = "io.github.paperwatch"


def watch_command() -> list[str]:
    """The command line that starts the watcher with the current installation."""
    if getattr(sys, "frozen", False):  # PyInstaller binary
        return [sys.executable, "watch", "--log-file", str(log_path())]
    exe = sys.executable
    if sys.platform == "win32":
        pythonw = Path(exe).with_name("pythonw.exe")
        if pythonw.exists():
            exe = str(pythonw)
    return [exe, "-m", "paperwatch", "watch", "--log-file", str(log_path())]


# ---------------------------------------------------------------- macOS
def _plist_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / f"{LABEL}.plist"


def _plist(cmd: list[str]) -> str:
    from xml.sax.saxutils import escape

    args = "\n".join(f"        <string>{escape(c)}</string>" for c in cmd)
    return f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>{LABEL}</string>
    <key>ProgramArguments</key>
    <array>
{args}
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>ProcessType</key>
    <string>Background</string>
</dict>
</plist>
"""


def _install_macos(cmd: list[str]) -> str:
    plist = _plist_path()
    plist.parent.mkdir(parents=True, exist_ok=True)
    domain = f"gui/{os.getuid()}"
    subprocess.run(["launchctl", "bootout", domain, str(plist)], capture_output=True)
    plist.write_text(_plist(cmd), encoding="utf-8")
    subprocess.run(["launchctl", "bootstrap", domain, str(plist)], check=True)
    return f"LaunchAgent installed: {plist}"


def _uninstall_macos() -> str:
    plist = _plist_path()
    subprocess.run(["launchctl", "bootout", f"gui/{os.getuid()}", str(plist)], capture_output=True)
    plist.unlink(missing_ok=True)
    return "LaunchAgent removed"


# ---------------------------------------------------------------- Linux
def _unit_path() -> Path:
    base = Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / "systemd" / "user" / "paperwatch.service"


def _unit(cmd: list[str]) -> str:
    import shlex

    return f"""[Unit]
Description=paperwatch - rename downloaded scientific papers

[Service]
ExecStart={shlex.join(cmd)}
Restart=on-failure
RestartSec=10

[Install]
WantedBy=default.target
"""


def _install_linux(cmd: list[str]) -> str:
    if not shutil.which("systemctl"):
        raise SystemExit(
            "systemctl not found. Add this command to your desktop's autostart instead:\n  "
            + " ".join(cmd))
    unit = _unit_path()
    unit.parent.mkdir(parents=True, exist_ok=True)
    unit.write_text(_unit(cmd), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    subprocess.run(["systemctl", "--user", "enable", "--now", "paperwatch.service"], check=True)
    subprocess.run(["systemctl", "--user", "restart", "paperwatch.service"], check=True)
    return f"systemd user service installed: {unit}"


def _uninstall_linux() -> str:
    subprocess.run(["systemctl", "--user", "disable", "--now", "paperwatch.service"],
                   capture_output=True)
    _unit_path().unlink(missing_ok=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return "systemd user service removed"


# ---------------------------------------------------------------- Windows
def _startup_path() -> Path:
    appdata = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    return appdata / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / "paperwatch.vbs"


def _vbs(cmd: list[str]) -> str:
    # VBScript: double quotes are escaped by doubling them. Window style 0 = hidden.
    line = " ".join(f'""{c}""' for c in cmd)
    return f'CreateObject("WScript.Shell").Run "{line}", 0, False\n'


def _install_windows(cmd: list[str]) -> str:
    path = _startup_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_vbs(cmd), encoding="utf-8")
    subprocess.Popen(["wscript.exe", str(path)],
                     creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
    return f"Startup launcher installed: {path}"


def _uninstall_windows() -> str:
    _startup_path().unlink(missing_ok=True)
    return ("Startup launcher removed. A watcher that is already running stops at next "
            "logout (or end the 'pythonw'/'paperwatch' process in Task Manager).")


# ---------------------------------------------------------------- public
def install() -> str:
    cmd = watch_command()
    log_path().parent.mkdir(parents=True, exist_ok=True)
    if sys.platform == "darwin":
        return _install_macos(cmd)
    if sys.platform == "win32":
        return _install_windows(cmd)
    return _install_linux(cmd)


def uninstall() -> str:
    if sys.platform == "darwin":
        return _uninstall_macos()
    if sys.platform == "win32":
        return _uninstall_windows()
    return _uninstall_linux()
