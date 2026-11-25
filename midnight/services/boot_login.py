"""Midnight Core Control Center: read-only GDM, authorized Plymouth changes."""

import configparser
import json
import os
import re
import shutil
import stat
import subprocess
from datetime import datetime
from pathlib import Path


BOOT_BACKUP_DIR = Path.home() / ".config/midnight-core-backup/boot-login"
GDM_DIR = Path("/etc/dconf/db/gdm.d")
THEME_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.+-]{0,127}$")


def _command(argv, timeout=6):
    try:
        return subprocess.run(
            argv, capture_output=True, text=True,
            check=False, timeout=timeout,
        )
    except (OSError, subprocess.TimeoutExpired):
        return None


def _write_private_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    # Create in a private directory, avoiding a symlink destination.
    temporary = path.with_name(path.name + ".new")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        temporary.replace(path)
    finally:
        if temporary.exists():
            temporary.unlink()


def _read_gdm_logo():
    """Read the explicitly configured dconf logo without changing GDM."""
    if not GDM_DIR.is_dir():
        return "Not configured", "No /etc/dconf/db/gdm.d directory"

    logo = None
    sources = []
    for path in sorted(GDM_DIR.iterdir()):
        if not path.is_file() or path.name.startswith("."):
            continue
        try:
            config = configparser.ConfigParser(interpolation=None, strict=False)
            config.optionxform = str
            config.read(path, encoding="utf-8")
            section = "org/gnome/login-screen"
            if config.has_option(section, "logo"):
                logo = config.get(section, "logo").strip().strip("\"'")
                sources.append(path.name)
        except (OSError, UnicodeError, configparser.Error):
            continue

    return (logo or "Not configured", ", ".join(sources) or "No logo override found")


def _trusted_executable(path):
    """Only run OS-owned, non-writable system executables as administrator."""
    try:
        target = Path(path)
        info = target.stat()
        if not target.is_file() or not (info.st_mode & stat.S_IXUSR):
            return None
        if info.st_uid != 0 or (info.st_mode & (stat.S_IWGRP | stat.S_IWOTH)):
            return None
        return str(target)
    except OSError:
        return None


class BootLoginService:
    def __init__(self):
        self.plymouth_exe = _trusted_executable(
            "/usr/bin/plymouth-set-default-theme"
        )
        self.pkexec_exe = _trusted_executable("/usr/bin/pkexec")

    def themes(self):
        if not self.plymouth_exe:
            return []
        result = _command([self.plymouth_exe, "--list"])
        if result is None or result.returncode != 0:
            return []
        return sorted({
            line.strip() for line in result.stdout.splitlines()
            if THEME_NAME.fullmatch(line.strip())
        }, key=str.casefold)

    def current_theme(self):
        if not self.plymouth_exe:
            return None
        result = _command([self.plymouth_exe])
        if result is None or result.returncode != 0:
            return None
        value = result.stdout.strip()
        return value if THEME_NAME.fullmatch(value) else None

    def gdm_info(self):
        service_name = None
        status = "Unknown"
        if shutil.which("systemctl"):
            for candidate in ("gdm.service", "display-manager.service"):
                result = _command(["systemctl", "is-active", candidate], timeout=3)
                if result and result.stdout.strip() == "active":
                    status = "Active"
                    service_name = candidate
                    break
            else:
                status = "Not detected as active"
        logo, source = _read_gdm_logo()
        return {
            "status": status,
            "service": service_name or "GDM / display-manager",
            "logo": logo,
            "logo_source": source,
            "custom_conf": "Present" if Path("/etc/gdm/custom.conf").is_file() else "Not found",
        }

    def snapshot(self):
        return {
            "themes": self.themes(),
            "current": self.current_theme(),
            "gdm": self.gdm_info(),
        }

    def preview_image(self, theme):
        if not THEME_NAME.fullmatch(theme):
            return None
        if theme not in self.themes():
            return None
        folder = Path("/usr/share/plymouth/themes") / theme
        if not folder.is_dir():
            return None
        # Preview is only an asset, not a simulation of the boot animation.
        choices = ["logo.png", "boot.png", "background.png", "watermark.png"]
        choices.extend([p.name for p in sorted(folder.glob("*.png"))][:12])
        for name in choices:
            path = folder / name
            try:
                if path.is_file() and path.stat().st_size <= 5_000_000:
                    return path
            except OSError:
                pass
        return None

    def privileged_command(self, theme):
        """Build strictly argument-separated pkexec command from installed names."""
        if not isinstance(theme, str) or not THEME_NAME.fullmatch(theme):
            raise ValueError("Invalid theme name")
        if theme not in self.themes():
            raise ValueError("Theme is not in Plymouth's installed theme list")
        if not self.plymouth_exe:
            raise FileNotFoundError("plymouth-set-default-theme not installed")
        if not self.pkexec_exe:
            raise FileNotFoundError("pkexec is not installed")
        return [self.pkexec_exe, self.plymouth_exe, theme, "--rebuild-initrd"]

    def record_success(self, previous, selected):
        """Record a *completed* theme change for a later authorized restore."""
        if not previous or not THEME_NAME.fullmatch(previous):
            return None
        BOOT_BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        name = "boot-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
        path = BOOT_BACKUP_DIR / name
        _write_private_json(path, {
            "previous": previous,
            "selected": selected,
            "created_at": datetime.now().isoformat(timespec="seconds"),
        })
        _write_private_json(BOOT_BACKUP_DIR / "latest.json", {"backup": name})
        return path

    def previous_theme(self):
        pointer = BOOT_BACKUP_DIR / "latest.json"
        if not pointer.is_file():
            return None
        try:
            name = json.loads(pointer.read_text(encoding="utf-8"))["backup"]
            if not isinstance(name, str) or Path(name).name != name:
                return None
            data = json.loads((BOOT_BACKUP_DIR / name).read_text(encoding="utf-8"))
            value = data.get("previous")
            return value if isinstance(value, str) and THEME_NAME.fullmatch(value) else None
        except (OSError, ValueError, KeyError, TypeError):
            return None
