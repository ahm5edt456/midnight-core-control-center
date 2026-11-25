"""Managed Bash aliases: existing user aliases remain read-only."""
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import os
import re
import shlex
import subprocess
import tempfile

NAME_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_-]{0,63}$')


@dataclass(frozen=True)
class AliasItem:
    name: str
    command: str
    source: str
    editable: bool


def parse_aliases(content):
    result = {}
    for line in content.splitlines():
        if not line.lstrip().startswith('alias '):
            continue
        try:
            parts = shlex.split(line.strip(), comments=False, posix=True)
        except ValueError:
            continue
        if len(parts) != 2 or parts[0] != 'alias' or '=' not in parts[1]:
            continue
        name, value = parts[1].split('=', 1)
        if NAME_RE.fullmatch(name):
            result[name] = value
    return result


class AliasService:
    def __init__(self, home=None):
        self.home = Path(home) if home is not None else Path.home()
        self.base = self.home / '.config/midnight-core/aliases.bash'
        self.managed = self.home / '.config/midnight-core/managed-aliases.bash'
        self.bashrc = self.home / '.bashrc'
        self.backups = self.home / '.config/midnight-core-backup/alias-manager'

    @staticmethod
    def _read(path):
        try:
            return path.read_text(encoding='utf-8')
        except FileNotFoundError:
            return ''

    def external(self):
        output = {}
        for source, path in [('Bash', self.bashrc), ('Midnight', self.base)]:
            for name, command in parse_aliases(self._read(path)).items():
                output[name] = AliasItem(name, command, source, False)
        return output

    def managed_aliases(self):
        return parse_aliases(self._read(self.managed))

    def list_aliases(self):
        records = self.external()
        for name, command in self.managed_aliases().items():
            records[name] = AliasItem(name, command, 'Managed', True)
        return sorted(records.values(), key=lambda r: r.name.casefold())

    @staticmethod
    def validate(name, command):
        if not NAME_RE.fullmatch(name):
            raise ValueError('Alias name: letters, numbers, _ or - (starts with a letter or _).')
        if not command.strip() or len(command) > 500:
            raise ValueError('Command must be 1–500 characters long.')
        if any(c in command for c in ('\n', '\r', '\x00')):
            raise ValueError('A command must be on one line.')

    def _save(self, aliases):
        parent = self.managed.parent
        parent.mkdir(parents=True, exist_ok=True)
        self.backups.mkdir(parents=True, exist_ok=True)
        self.backups.chmod(0o700)
        stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        backup = self.backups / f'managed-{stamp}.bash'
        backup.write_text(self._read(self.managed), encoding='utf-8')
        backup.chmod(0o600)
        body = '# Managed by Midnight Core Control Center — edit in the app\n'
        body += ''.join(f'alias {n}={shlex.quote(v)}\n' for n, v in sorted(aliases.items()))
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile('w', dir=parent, prefix='.aliases-',
                                             encoding='utf-8', delete=False) as f:
                tmp_path = Path(f.name)
                f.write(body)
            os.chmod(tmp_path, 0o600)
            result = subprocess.run(['bash', '-n', str(tmp_path)],
                                    capture_output=True, text=True, timeout=4)
            if result.returncode:
                raise ValueError('Bash syntax validation failed: ' + result.stderr.strip())
            os.replace(tmp_path, self.managed)
        finally:
            if tmp_path is not None:
                tmp_path.unlink(missing_ok=True)
        pointer = self.backups / 'latest.json'
        pointer.write_text(json.dumps({'file': backup.name}), encoding='utf-8')
        pointer.chmod(0o600)
        return backup

    def save(self, name, command, original=None):
        self.validate(name, command)
        existing = self.managed_aliases()
        external = self.external()
        if name in external:
            raise ValueError(f'{name} is defined outside the managed file; it is read-only.')
        if original and original not in existing:
            raise ValueError('Original alias is not managed.')
        if name in existing and original != name:
            raise ValueError('Alias already exists; select Edit instead.')
        if original and original != name:
            existing.pop(original)
        existing[name] = command
        return self._save(existing)

    def delete(self, name):
        existing = self.managed_aliases()
        if name not in existing:
            raise ValueError('Only managed aliases can be deleted.')
        del existing[name]
        return self._save(existing)

    def restore_previous(self):
        pointer = self.backups / 'latest.json'
        if not pointer.exists():
            raise FileNotFoundError('No alias backup exists.')
        name = json.loads(pointer.read_text(encoding='utf-8'))['file']
        if Path(name).name != name:
            raise ValueError('Invalid backup name.')
        restored = parse_aliases((self.backups / name).read_text(encoding='utf-8'))
        # Do not overwrite an alias that now exists in a read-only source.
        conflict = set(restored) & set(self.external())
        if conflict:
            raise ValueError('Conflicting external aliases: ' + ', '.join(sorted(conflict)))
        return self._save(restored)
