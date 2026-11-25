"""Read GNOME Shell extension state; never invoke commands through a shell."""
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
import subprocess


class ExtensionError(RuntimeError):
    pass


@dataclass(frozen=True)
class Extension:
    uuid: str
    name: str
    description: str
    enabled: bool
    system: bool


class ExtensionService:
    def __init__(self, home=None, command='gnome-extensions'):
        self.home = Path(home) if home is not None else Path.home()
        self.command = command
        self.system_dir = Path('/usr/share/gnome-shell/extensions')
        self.user_dir = self.home / '.local/share/gnome-shell/extensions'

    def _run(self, *args, timeout=12):
        if not shutil.which(self.command):
            raise ExtensionError('gnome-extensions is not installed or not in PATH')
        try:
            result = subprocess.run(
                [self.command, *args], capture_output=True, text=True,
                check=False, timeout=timeout,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ExtensionError(f'GNOME command failed: {exc}') from exc
        if result.returncode != 0:
            raise ExtensionError((result.stderr or result.stdout).strip() or
                                 f'gnome-extensions returned {result.returncode}')
        return result.stdout

    def _metadata(self, uuid):
        for root in (self.user_dir, self.system_dir):
            path = root / uuid / 'metadata.json'
            if not path.is_file():
                continue
            try:
                info = json.loads(path.read_text(encoding='utf-8'))
            except (OSError, ValueError):
                continue
            return (str(info.get('name') or uuid),
                    str(info.get('description') or '').replace('\n', ' ')[:240],
                    root == self.system_dir)
        return uuid, '', False

    def list_extensions(self):
        uuids = sorted(set(self._run('list').splitlines()))
        enabled = set(self._run('list', '--enabled').splitlines())
        output = []
        for uuid in uuids:
            uuid = uuid.strip()
            if not uuid or '/' in uuid or '\x00' in uuid:
                continue
            name, description, system = self._metadata(uuid)
            output.append(Extension(uuid, name, description, uuid in enabled, system))
        return sorted(output, key=lambda x: x.name.casefold())

    def set_enabled(self, uuid, enable):
        # Only permit UUIDs returned from the live GNOME list.
        known = {item.uuid for item in self.list_extensions()}
        if uuid not in known:
            raise ExtensionError('Extension is not installed: ' + uuid)
        self._run('enable' if enable else 'disable', uuid)

    def open_preferences(self, uuid):
        known = {item.uuid for item in self.list_extensions()}
        if uuid not in known:
            raise ExtensionError('Extension is not installed: ' + uuid)
        try:
            subprocess.Popen([self.command, 'prefs', uuid], start_new_session=True)
        except OSError as exc:
            raise ExtensionError(str(exc)) from exc
