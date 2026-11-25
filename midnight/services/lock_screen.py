"""Safe GSettings integration for the user's Midnight Lock V3 extension."""

import json
import os
from datetime import datetime
from pathlib import Path

from gi.repository import Gio


EXT_UUID = "midnight-lock@local"
SCHEMA_ID = "org.gnome.shell.extensions.midnight-lock"
EXTENSION_DIR = Path.home() / ".local/share/gnome-shell/extensions" / EXT_UUID
SCHEMA_DIR = EXTENSION_DIR / "schemas"
BACKUP_DIR = Path.home() / ".config/midnight-core-backup/lock-screen"

TOGGLES = (
    "breathing-glow",
    "slide-animation",
    "avatar-glow",
    "modern-clock",
)
CHOICES = {
    "accent-color": (
        "Arctic Blue", "Midnight Gold", "Aurora Green",
        "Royal Violet", "Ice Silver", "Crimson Red",
    ),
    "animation-speed": ("Slow", "Normal", "Fast"),
    "glow-intensity": ("Low", "Medium", "High"),
}


class LockScreenService:
    def __init__(self):
        if not EXTENSION_DIR.is_dir():
            raise FileNotFoundError(f"Missing extension: {EXTENSION_DIR}")
        if not (SCHEMA_DIR / "gschemas.compiled").is_file():
            raise FileNotFoundError(
                f"Missing compiled GSettings schema in {SCHEMA_DIR}. "
                "Run glib-compile-schemas on this directory."
            )

        source = Gio.SettingsSchemaSource.new_from_directory(
            str(SCHEMA_DIR), Gio.SettingsSchemaSource.get_default(), False
        )
        schema = source.lookup(SCHEMA_ID, False)
        if schema is None:
            raise RuntimeError(f"GSettings schema {SCHEMA_ID} not found")

        for key in TOGGLES:
            self._check_type(schema, key, "b")
        for key in CHOICES:
            self._check_type(schema, key, "u")

        self.settings = Gio.Settings.new_full(schema, None, None)

    @staticmethod
    def _check_type(schema, name, expected):
        if name not in schema.list_keys():
            raise RuntimeError(f"Missing GSettings key: {name}")
        actual = schema.get_key(name).get_value_type().dup_string()
        if actual != expected:
            raise RuntimeError(
                f"Unexpected type for {name}: {actual} (expected {expected})"
            )

    @staticmethod
    def _validate(values):
        allowed = set(TOGGLES) | set(CHOICES)
        if set(values) != allowed:
            raise ValueError("Lock screen settings are incomplete or unknown")
        for key in TOGGLES:
            if type(values[key]) is not bool:
                raise ValueError(f"Invalid toggle: {key}")
        for key, choices in CHOICES.items():
            if type(values[key]) is not int or not 0 <= values[key] < len(choices):
                raise ValueError(f"Invalid choice: {key}")

    def read(self):
        return {
            **{name: self.settings.get_boolean(name) for name in TOGGLES},
            **{name: self.settings.get_uint(name) for name in CHOICES},
        }

    def _write(self, values):
        self._validate(values)
        for key in values:
            if not self.settings.is_writable(key):
                raise PermissionError(f"GSettings key is read-only: {key}")
        for key in TOGGLES:
            if self.settings.get_boolean(key) != values[key]:
                if not self.settings.set_boolean(key, values[key]):
                    raise RuntimeError(f"Could not change {key}")
        for key in CHOICES:
            if self.settings.get_uint(key) != values[key]:
                if not self.settings.set_uint(key, values[key]):
                    raise RuntimeError(f"Could not change {key}")

    @staticmethod
    def _save_json(path, data):
        # User-only permissions even if the default umask is permissive.
        fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
            stream.write("\n")

    def apply(self, values):
        self._validate(values)
        before = self.read()
        if values == before:
            return None

        BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        filename = "lock-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".json"
        backup = BACKUP_DIR / filename
        self._save_json(backup, before)

        try:
            self._write(values)
        except Exception as error:
            try:
                self._write(before)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Apply failed: {error}. Rollback also failed: {rollback_error}. "
                    f"Original settings saved in {backup}"
                ) from error
            raise

        # Update last-known restore point only after a successful apply.
        pointer = BACKUP_DIR / "latest.json"
        temporary = BACKUP_DIR / ".latest.tmp"
        if temporary.exists():
            temporary.unlink()
        self._save_json(temporary, {"backup": filename})
        temporary.replace(pointer)
        return backup

    def restore_previous(self):
        pointer = BACKUP_DIR / "latest.json"
        if not pointer.is_file():
            raise FileNotFoundError("No previous lock screen backup found")
        name = json.loads(pointer.read_text(encoding="utf-8"))["backup"]
        if not isinstance(name, str) or Path(name).name != name:
            raise ValueError("Invalid backup filename")
        backup = BACKUP_DIR / name
        original = json.loads(backup.read_text(encoding="utf-8"))
        self._validate(original)

        current = self.read()
        try:
            self._write(original)
        except Exception as error:
            try:
                self._write(current)
            except Exception as rollback_error:
                raise RuntimeError(
                    f"Restore failed: {error}; rollback failed: {rollback_error}"
                ) from error
            raise
        return backup
