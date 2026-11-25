"""Safe, focused settings editor for Midnight Core Terminal & Neovim page.

Only changes managed keys; creates restricted backups; never invokes sudo.
"""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
import re
import tempfile
import tomllib
from datetime import datetime
from typing import Any

HOME = Path.home()
ALACRITTY = HOME / ".config/alacritty/alacritty.toml"
STARSHIP = HOME / ".config/starship.toml"
NVIM_OPTIONS = HOME / ".config/nvim/lua/config/options.lua"
NVIM_THEME = HOME / ".config/nvim/lua/plugins/midnight-core.lua"
BACKUP_DIR = HOME / ".config/midnight-core-backup/terminal-neovim"

START = "-- MIDNIGHT CONTROL CENTER BEGIN"
END = "-- MIDNIGHT CONTROL CENTER END"

ALLOWED = {
    "alacritty.font_family": (ALACRITTY, "font.normal", "family"),
    "alacritty.font_size": (ALACRITTY, "font", "size"),
    "alacritty.opacity": (ALACRITTY, "window", "opacity"),
    "starship.add_newline": (STARSHIP, "", "add_newline"),
    "starship.hide_python": (STARSHIP, "python", "disabled"),
    "starship.hide_git_branch": (STARSHIP, "git_branch", "disabled"),
}
NVIM_ALLOWED = {
    "nvim.number": "number",
    "nvim.relativenumber": "relativenumber",
    "nvim.wrap": "wrap",
    "nvim.cursorline": "cursorline",
}
DEFAULTS = {
    "alacritty.font_family": "JetBrainsMono Nerd Font",
    "alacritty.font_size": 12.0,
    "alacritty.opacity": 1.0,
    "starship.add_newline": True,
    "starship.hide_python": False,
    "starship.hide_git_branch": False,
    "nvim.number": True,
    "nvim.relativenumber": False,
    "nvim.wrap": False,
    "nvim.cursorline": True,
}


def parse_toml(path: Path) -> dict:
    if not path.exists():
        return {}
    with path.open("rb") as stream:
        return tomllib.load(stream)


def nested(data: dict, section: str, key: str, fallback: Any):
    for part in section.split(".") if section else []:
        if not isinstance(data, dict):
            return fallback
        data = data.get(part, {})
    return data.get(key, fallback) if isinstance(data, dict) else fallback


def encode_toml(value: Any) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return str(value)
    if isinstance(value, str):
        return json.dumps(value, ensure_ascii=False)
    raise ValueError("Unsupported TOML value")


def edit_toml(original: str, changes: dict[tuple[str, str], Any]) -> str:
    """Patch literal table assignments, keeping other fields/comments intact.

    Invalid/complex TOML returns an error rather than guessing. Existing import
    statements are checked by caller before this routine is used.
    """
    tomllib.loads(original)
    lines = original.splitlines(keepends=True)
    table = ""
    changed = set()
    table_positions = {}
    header = re.compile(r"^\s*\[([A-Za-z0-9_.-]+)\]\s*(?:#.*)?$")
    assign = re.compile(r"^(\s*)([A-Za-z_][A-Za-z_0-9-]*)(\s*=\s*)(.*?)(\r?\n)?$")

    for i, line in enumerate(lines):
        match = header.match(line.rstrip("\r\n"))
        if match:
            table = match.group(1)
            table_positions[table] = i
            continue
        assignment = assign.match(line)
        if not assignment:
            continue
        key = (table, assignment.group(2))
        if key in changes:
            # Preserve trailing simple comments if present and unambiguous.
            old_value = assignment.group(4)
            suffix = ""
            if " #" in old_value and not old_value.lstrip().startswith(('"', "'")):
                suffix = "  #" + old_value.split(" #", 1)[1]
            lines[i] = (
                assignment.group(1) + assignment.group(2) + assignment.group(3)
                + encode_toml(changes[key]) + suffix
                + (assignment.group(5) or "\n")
            )
            changed.add(key)

    missing = set(changes) - changed
    # For a missing field in an existing table, insert at the end of that table.
    # Group insertions and process from bottom to top to preserve indexes.
    for section in sorted({s for s, _ in missing}, key=lambda v: table_positions.get(v, -1), reverse=True):
        edits = [(key, changes[section, key]) for s, key in sorted(missing) if s == section]
        block = [f"{key} = {encode_toml(value)}\n" for key, value in edits]
        if section in table_positions:
            start = table_positions[section] + 1
            end = next((j for j in range(start, len(lines)) if lines[j].lstrip().startswith("[")), len(lines))
            lines[end:end] = block
        elif not section:
            # TOML top-level values must appear before any [table].
            first_header = next((j for j, line in enumerate(lines) if line.lstrip().startswith("[")), len(lines))
            lines[first_header:first_header] = block
        else:
            if lines and not lines[-1].endswith("\n"):
                lines[-1] += "\n"
            if lines and lines[-1].strip():
                lines.append("\n")
            lines.append(f"[{section}]\n")
            lines.extend(block)

    result = "".join(lines)
    tomllib.loads(result)  # refuse to write an invalid config
    return result


def edit_nvim(original: str, changes: dict[str, bool]) -> str:
    begin = original.find(START)
    end = original.find(END)
    if (begin >= 0) != (end >= 0):
        raise ValueError("Incomplete managed Neovim block; edit manually")
    if begin >= 0 and end <= begin:
        raise ValueError("Invalid managed Neovim block")
    managed = {}
    if begin >= 0:
        inside = original[begin + len(START):end]
        for key, value in re.findall(r"vim\.opt\.([a-z]+)\s*=\s*(true|false)", inside):
            if key in NVIM_ALLOWED.values():
                managed[key] = value == "true"
    for item, value in changes.items():
        managed[NVIM_ALLOWED[item]] = value
    lines = [START] + [f"vim.opt.{key} = {'true' if val else 'false'}" for key, val in sorted(managed.items())] + [END]
    block = "\n".join(lines)
    if begin >= 0:
        return original[:begin] + block + original[end + len(END):]
    return original.rstrip() + "\n\n" + block + "\n"


def atomic_write(path: Path, contents: bytes):
    path.parent.mkdir(parents=True, exist_ok=True)
    previous_mode = (path.stat().st_mode & 0o777) if path.exists() else 0o600
    descriptor, temp_name = tempfile.mkstemp(prefix=".midnight-", dir=path.parent)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(contents)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_name, previous_mode)
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


class DeveloperSettingsService:
    def __init__(self):
        self.paths = {ALACRITTY, STARSHIP, NVIM_OPTIONS}

    def read(self):
        alacritty = parse_toml(ALACRITTY)
        starship = parse_toml(STARSHIP)
        nvim_text = NVIM_OPTIONS.read_text() if NVIM_OPTIONS.is_file() else ""
        values = dict(DEFAULTS)
        for code, (path, section, key) in ALLOWED.items():
            values[code] = nested(
                alacritty if path == ALACRITTY else starship,
                section, key, DEFAULTS[code],
            )
        # Read own settings first, then explicit unambiguous previous options.
        for code, option in NVIM_ALLOWED.items():
            match = list(re.finditer(
                rf"vim\.opt\.{option}\s*=\s*(true|false)\b", nvim_text
            ))
            if match:
                values[code] = match[-1].group(1) == "true"
        # Alacritty can use other imported files. Don't override them blindly.
        imports = alacritty.get("general", {}).get("import", [])
        values["alacritty.has_imports"] = bool(imports)
        values["alacritty.exists"] = ALACRITTY.exists()
        values["nvim.exists"] = NVIM_OPTIONS.exists()
        return values

    def apply(self, proposed: dict):
        current = self.read()
        changes = {}
        for key, value in proposed.items():
            if key not in ALLOWED and key not in NVIM_ALLOWED:
                raise ValueError(f"Unexpected setting: {key}")
            if key.startswith("nvim.") or key.startswith("starship."):
                if type(value) is not bool:
                    raise ValueError(f"Expected a switch for {key}")
            elif key == "alacritty.font_family":
                if not isinstance(value, str) or not value.strip() or len(value) > 120:
                    raise ValueError("Invalid Alacritty font family")
            elif key == "alacritty.font_size":
                if type(value) not in (float, int) or not 4 <= value <= 100:
                    raise ValueError("Font size must be between 4 and 100")
            elif key == "alacritty.opacity":
                if type(value) not in (float, int) or not 0 <= value <= 1:
                    raise ValueError("Opacity must be between 0 and 1")
            if current[key] != value:
                changes[key] = value
        if not changes:
            return None
        if current["alacritty.has_imports"] and any(k.startswith("alacritty.") for k in changes):
            raise ValueError("Alacritty imports external TOML files; edit manually to avoid overriding imported values")
        if any(k.startswith("nvim.") for k in changes) and not NVIM_OPTIONS.exists():
            raise FileNotFoundError("Existing Neovim options.lua not found")

        planned = {}
        for path in (ALACRITTY, STARSHIP, NVIM_OPTIONS):
            if path.is_symlink():
                raise ValueError(f"Configuration is a symlink: {path}. Edit the original manually")
        for path in (ALACRITTY, STARSHIP):
            target = {
                (section, key): changes[code]
                for code, (p, section, key) in ALLOWED.items()
                if p == path and code in changes
            }
            if target:
                existing = path.read_text() if path.exists() else ""
                planned[path] = edit_toml(existing, target).encode("utf-8")
        nvim_changes = {k: v for k, v in changes.items() if k in NVIM_ALLOWED}
        if nvim_changes:
            planned[NVIM_OPTIONS] = edit_nvim(
                NVIM_OPTIONS.read_text(), nvim_changes
            ).encode("utf-8")
        original = {str(path): (base64.b64encode(path.read_bytes()).decode("ascii") if path.exists() else None) for path in planned}
        BACKUP_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        BACKUP_DIR.chmod(0o700)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        archive = BACKUP_DIR / f"before-{stamp}.json"
        atomic_write(archive, json.dumps({"original": original}, indent=2).encode())
        written = []
        try:
            for path, contents in planned.items():
                atomic_write(path, contents)
                written.append(path)
        except Exception:
            for path in reversed(written):
                old = original[str(path)]
                if old is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_write(path, base64.b64decode(old))
            raise
        atomic_write(BACKUP_DIR / "latest.json", json.dumps({"backup": archive.name}).encode())
        return archive

    def restore_previous(self):
        pointer = json.loads((BACKUP_DIR / "latest.json").read_text())
        name = pointer["backup"]
        if Path(name).name != name:
            raise ValueError("Invalid backup filename")
        backup = BACKUP_DIR / name
        data = json.loads(backup.read_text())["original"]
        allowed_paths = {str(p) for p in self.paths}
        if not set(data).issubset(allowed_paths):
            raise ValueError("Backup includes unexpected file paths")
        # Save a restore checkpoint before overwriting anything.
        checkpoint = BACKUP_DIR / f"pre-restore-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}.json"
        present = {s: (base64.b64encode(Path(s).read_bytes()).decode() if Path(s).exists() else None) for s in data}
        atomic_write(checkpoint, json.dumps({"original": present}, indent=2).encode())
        for pathstr, encoded in data.items():
            path = Path(pathstr)
            if path.is_symlink():
                raise ValueError(f"Cannot restore over a symlink: {path}")
            if encoded is None:
                path.unlink(missing_ok=True)
            else:
                atomic_write(path, base64.b64decode(encoded, validate=True))
        # Subsequent restore reverses this restore (avoids repeated stale restores).
        atomic_write(BACKUP_DIR / "latest.json", json.dumps({"backup": checkpoint.name}).encode())
        return backup
