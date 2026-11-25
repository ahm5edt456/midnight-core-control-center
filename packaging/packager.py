#!/usr/bin/env python3
"""Midnight Core Control Center: unprivileged, per-user GNOME package installer."""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import shlex
import shutil
import stat
import sys
import tempfile
from datetime import datetime


APP_ID = "io.midnightcore.ControlCenter"
APP_NAME = "Midnight Core Control Center"
MANAGED_DESKTOP = "X-MidnightCore-Managed=true"
MANAGED_LAUNCHER = "# Midnight Core Stage 11 managed launcher"
MANAGED_ICON = "<!-- Midnight Core Stage 11 managed icon -->"
MANAGED_APP_MARKER = ".midnight-core-stage11"
DEFAULT_PROJECT = Path.home() / "Projects/midnight-core-control-center"
BUNDLE = Path(__file__).resolve().parent


class PackagingError(RuntimeError):
    pass


def paths():
    home = Path.home()
    data_home = Path(os.environ.get("XDG_DATA_HOME", str(home / ".local/share"))).expanduser()
    bin_home = Path(os.environ.get("XDG_BIN_HOME", str(home / ".local/bin"))).expanduser()
    if not data_home.is_absolute() or not bin_home.is_absolute():
        raise PackagingError("XDG_DATA_HOME and XDG_BIN_HOME must be absolute paths")
    root = data_home / "midnight-core-control-center"
    return {
        "data_home": data_home,
        "bin_home": bin_home,
        "root": root,
        "app": root / "app",
        "launcher": bin_home / "midnight-control-center",
        "desktop": data_home / "applications" / (APP_ID + ".desktop"),
        "icon": data_home / "icons/hicolor/scalable/apps" / (APP_ID + ".svg"),
    }


def check_not_root():
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        raise PackagingError("Run as your normal user, not with sudo or as root")


def read_text(path):
    return path.read_text(encoding="utf-8")


def assert_owned(path, marker: str):
    if path.is_symlink():
        raise PackagingError(f"Refusing to replace symlink: {path}")
    if path.exists() and marker not in read_text(path):
        raise PackagingError(f"Existing unrecognized file; refusing overwrite: {path}")


def validate_project(project: Path):
    if not project.is_dir():
        raise PackagingError(f"Project folder is missing: {project}")
    required = [project / "main.py", project / "midnight/application.py", project / "midnight/window.py", project / "assets/style.css"]
    for file in required:
        if not file.is_file():
            raise PackagingError(f"Required project file missing: {file}")
    app_code = read_text(project / "midnight/application.py")
    if APP_ID not in app_code:
        raise PackagingError(f"Application ID must match desktop entry: {APP_ID}")


def safe_copy_project(project: Path, target: Path):
    target.mkdir(parents=True, exist_ok=True)
    allowed = {".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".json", ".ui", ".gresource"}
    files = [project / "main.py"]
    for top, accepted in (("midnight", {".py"}), ("assets", allowed)):
        parent = project / top
        if parent.is_symlink():
            raise PackagingError(f"Symlink directory not allowed: {parent}")
        for base, dirs, names in os.walk(parent, followlinks=False):
            src_dir = Path(base)
            for d in dirs:
                if (src_dir / d).is_symlink():
                    raise PackagingError(f"Symlink directory not allowed: {src_dir / d}")
            for name in names:
                candidate = src_dir / name
                if candidate.is_symlink():
                    raise PackagingError(f"Symlink file not allowed: {candidate}")
                if candidate.suffix.lower() in accepted:
                    files.append(candidate)
    for src in files:
        if src.is_symlink():
            raise PackagingError(f"Symlink file not allowed: {src}")
        rel = src.relative_to(project)
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
        if dest.suffix == ".py":
            try:
                compile(read_text(dest), str(dest), "exec")
            except SyntaxError as exc:
                raise PackagingError(f"Invalid Python source: {rel}: {exc}") from exc
    (target / MANAGED_APP_MARKER).write_text("Installed by Midnight Core Stage 11\n", encoding="utf-8")
    return len(files)


def desktop_quote(text: str):
    """Freedesktop quoted argument: escape reserved chars and disallow control chars."""
    if any(c in text for c in "\n\r\0"):
        raise PackagingError("Invalid launcher path")
    text = text.replace("\\", "\\\\").replace('"', '\\"').replace("$", "\\$").replace("`", "\\`")
    return '"' + text + '"'


def make_launcher(app_path: Path):
    executable = shlex.quote(str(app_path / "main.py"))
    directory = shlex.quote(str(app_path))
    return (
        "#!/bin/sh\n"
        + MANAGED_LAUNCHER + "\n"
        + "set -eu\n"
        + f"cd {directory}\n"
        + f"exec /usr/bin/python3 {executable} \"$@\"\n"
    ).encode("utf-8")


def make_desktop(launcher_path: Path):
    return (f"""[Desktop Entry]
Type=Application
Name={APP_NAME}
Name[ar]=مركز تحكم ميدنايت كور
Comment=Manage the Midnight Core Fedora workstation
Comment[ar]=إدارة تخصيصات وأدوات بيئة ميدنايت كور
Exec={desktop_quote(str(launcher_path))}
Icon={APP_ID}
Terminal=false
Categories=Settings;System;Development;
Keywords=Fedora;GNOME;Appearance;Neovim;Terminal;Backup;
StartupNotify=true
{MANAGED_DESKTOP}
""").encode("utf-8")


def atomic_write(path: Path, data: bytes, mode: int):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".midnight-stage11-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(name, mode)
        os.replace(name, path)
    finally:
        if os.path.lexists(name):
            os.unlink(name)


def install(project: Path):
    check_not_root()
    project = project.expanduser().resolve()
    validate_project(project)
    p = paths()
    if p["root"].is_symlink():
        raise PackagingError("Refusing symlinked application root")
    if p["app"].is_symlink():
        raise PackagingError("Refusing to modify symlinked application directory")
    if p["app"].exists() and not (p["app"] / MANAGED_APP_MARKER).is_file():
        raise PackagingError(f"Refusing to overwrite unknown app directory: {p['app']}")
    assert_owned(p["launcher"], MANAGED_LAUNCHER)
    assert_owned(p["desktop"], MANAGED_DESKTOP)
    assert_owned(p["icon"], MANAGED_ICON)
    p["root"].mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".stage11-", dir=p["root"]) as temp:
        temp_app = Path(temp) / "app"
        numfiles = safe_copy_project(project, temp_app)
        icon_data = (BUNDLE / "icon.svg").read_bytes()
        if MANAGED_ICON.encode() not in icon_data:
            raise PackagingError("Missing marker on packaged icon")
        targets = [
            (p["launcher"], make_launcher(p["app"]), 0o755),
            (p["desktop"], make_desktop(p["launcher"]), 0o644),
            (p["icon"], icon_data, 0o644),
        ]
        originals = {}
        for path, _data, _mode in targets:
            originals[path] = (path.read_bytes(), stat.S_IMODE(path.stat().st_mode)) if path.exists() else None
        old_app = None
        original_moved = False
        app_promoted = False
        try:
            if p["app"].exists():
                old_app = p["root"] / (".rollback-" + datetime.now().strftime("%Y%m%d%H%M%S%f"))
                p["app"].rename(old_app)
                original_moved = True
            temp_app.rename(p["app"])
            app_promoted = True
            for path, data, mode in targets:
                atomic_write(path, data, mode)
        except Exception:
            if app_promoted and p["app"].exists():
                shutil.rmtree(p["app"])
            if original_moved and old_app is not None and old_app.exists():
                old_app.rename(p["app"])
            for path, _data, _mode in targets:
                try:
                    previous = originals[path]
                    if previous is None:
                        path.unlink(missing_ok=True)
                    else:
                        atomic_write(path, *previous)
                except Exception as rollback_error:
                    print(f"WARNING: Could not restore {path}: {rollback_error}", file=sys.stderr)
            raise
        if old_app is not None:
            shutil.rmtree(old_app)
    print(f"Installed {APP_NAME}")
    print(f"Application files: {p['app']}")
    print(f"Files packaged: {numfiles}")
    print(f"Desktop entry: {p['desktop']}")
    print(f"Icon: {p['icon']}")
    print(f"Launch: {p['launcher']}")
    print(f"Or use: gtk-launch {APP_ID}")
    print("Your original project and configuration/backups remain untouched.")


def uninstall():
    check_not_root()
    p = paths()
    for path, marker in ((p["launcher"], MANAGED_LAUNCHER), (p["desktop"], MANAGED_DESKTOP), (p["icon"], MANAGED_ICON)):
        assert_owned(path, marker)
    if p["app"].is_symlink():
        raise PackagingError("Refusing to remove symlinked application directory")
    if p["app"].exists() and not (p["app"] / MANAGED_APP_MARKER).is_file():
        raise PackagingError("Refusing to remove unknown app directory")
    for path in (p["desktop"], p["launcher"], p["icon"]):
        path.unlink(missing_ok=True)
    if p["app"].exists():
        shutil.rmtree(p["app"])
    try:
        p["root"].rmdir()
    except OSError:
        pass
    print("Midnight Core Control Center application uninstalled.")
    print("Original project, user settings, and backup archives were not deleted.")


def status():
    p = paths()
    for key in ("app", "launcher", "desktop", "icon"):
        print(f"{key:<9}: {'present' if p[key].exists() else 'missing'}  {p[key]}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["install", "uninstall", "status"])
    parser.add_argument("--project", type=Path, default=DEFAULT_PROJECT)
    args = parser.parse_args()
    try:
        if args.command == "install":
            install(args.project)
        elif args.command == "uninstall":
            uninstall()
        else:
            status()
    except (PackagingError, OSError, ValueError) as error:
        parser.exit(1, f"ERROR: {error}\n")


if __name__ == "__main__":
    main()
