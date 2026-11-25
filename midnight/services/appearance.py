import json
from datetime import datetime
from pathlib import Path

from gi.repository import Gio


INTERFACE = "org.gnome.desktop.interface"
BACKGROUND = "org.gnome.desktop.background"

KEYS = {
    "scheme": (INTERFACE, "color-scheme"),
    "gtk": (INTERFACE, "gtk-theme"),
    "icons": (INTERFACE, "icon-theme"),
    "cursor": (INTERFACE, "cursor-theme"),
    "font": (INTERFACE, "font-name"),
    "document_font": (INTERFACE, "document-font-name"),
    "mono_font": (INTERFACE, "monospace-font-name"),
    "wallpaper_light": (BACKGROUND, "picture-uri"),
    "wallpaper_dark": (BACKGROUND, "picture-uri-dark"),
}

BACKUP_DIR = (
    Path.home()
    / ".config/midnight-core-backup/appearance"
)

THEME_DIRS = [
    Path("/usr/share/themes"),
    Path.home() / ".themes",
    Path.home() / ".local/share/themes",
]

ICON_DIRS = [
    Path("/usr/share/icons"),
    Path.home() / ".icons",
    Path.home() / ".local/share/icons",
]


def available_themes():
    names = {"Adwaita"}

    for directory in THEME_DIRS:
        if not directory.is_dir():
            continue

        for path in directory.iterdir():
            if path.is_dir() and (
                (path / "gtk-3.0").is_dir()
                or (path / "gtk-4.0").is_dir()
            ):
                names.add(path.name)

    return sorted(names, key=str.casefold)


def available_icons():
    names = {"Adwaita"}

    for directory in ICON_DIRS:
        if not directory.is_dir():
            continue

        for path in directory.iterdir():
            if path.is_dir() and (
                path / "index.theme"
            ).is_file():
                names.add(path.name)

    return sorted(names, key=str.casefold)


def available_cursors():
    names = {"Adwaita"}

    for directory in ICON_DIRS:
        if not directory.is_dir():
            continue

        for path in directory.iterdir():
            if path.is_dir() and (
                path / "cursors"
            ).is_dir():
                names.add(path.name)

    return sorted(names, key=str.casefold)


class AppearanceService:

    def __init__(self):
        self.settings = {
            INTERFACE: Gio.Settings.new(INTERFACE),
            BACKGROUND: Gio.Settings.new(BACKGROUND),
        }

    def snapshot(self):
        return {
            name: self.settings[schema].get_string(key)
            for name, (schema, key) in KEYS.items()
        }

    def _write(self, values):
        for name, value in values.items():
            if name not in KEYS:
                raise ValueError(
                    f"Unknown appearance setting: {name}"
                )

            if not isinstance(value, str):
                raise ValueError(
                    f"Invalid value for: {name}"
                )

            schema, key = KEYS[name]
            setting = self.settings[schema]

            if not setting.is_writable(key):
                raise PermissionError(
                    f"Setting is locked: {key}"
                )

            if setting.get_string(key) == value:
                continue

            if not setting.set_string(key, value):
                raise RuntimeError(
                    f"Cannot update setting: {key}"
                )

    def apply(self, values):
        before = self.snapshot()

        changes = {
            name: value
            for name, value in values.items()
            if name in before and before[name] != value
        }

        if not changes:
            return None

        BACKUP_DIR.mkdir(
            parents=True, exist_ok=True, mode=0o700
        )

        name = datetime.now().strftime(
            "appearance-%Y%m%d-%H%M%S-%f.json"
        )

        backup_path = BACKUP_DIR / name

        # Store the original settings before any change.
        backup_path.write_text(
            json.dumps(before, indent=2) + "\n"
        )
        backup_path.chmod(0o600)

        try:
            self._write(changes)
        except Exception:
            try:
                self._write(before)
            except Exception:
                pass
            raise

        (BACKUP_DIR / "latest.json").write_text(
            json.dumps({"backup": name}, indent=2) + "\n"
        )

        return backup_path

    def restore_previous(self):
        pointer = BACKUP_DIR / "latest.json"

        if not pointer.is_file():
            raise FileNotFoundError(
                "No previous appearance backup found"
            )

        name = json.loads(
            pointer.read_text()
        )["backup"]

        # Prevent an invalid backup path.
        if Path(name).name != name:
            raise ValueError("Invalid backup filename")

        backup = BACKUP_DIR / name
        values = json.loads(backup.read_text())

        current = self.snapshot()

        try:
            self._write(values)
        except Exception:
            try:
                self._write(current)
            except Exception:
                pass
            raise

        return backup
