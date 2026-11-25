"""Midnight Core backups of explicitly allowlisted user configuration paths.

No shell execution, no root paths, no arbitrary archive extraction, no symlinks.
A pre-restore rescue archive is created before any destination is replaced.
"""

import hashlib
import json
import os
import shutil
import stat
import tempfile
import uuid
import zipfile
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath

COMPONENTS = {
    'neovim': ('Neovim / LazyVim', '.config/nvim', 'dir'),
    'alacritty': ('Alacritty', '.config/alacritty', 'dir'),
    'starship': ('Starship', '.config/starship.toml', 'file'),
    'tmux': ('Tmux', '.tmux.conf', 'file'),
    'midnight': ('Midnight Core', '.config/midnight-core', 'dir'),
    'bash': ('Bash startup', '.bashrc', 'file'),
}

VERSION = 1
MAX_TOTAL_BYTES = 100 * 1024 * 1024
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_FILES = 3000
EXCLUDE_DIRS = {'.git', '.cache', '__pycache__', '.venv', 'node_modules'}
EXCLUDE_FILES = {'.env', 'credentials.json', 'auth.json', 'id_rsa', 'id_ed25519'}
EXCLUDE_SUFFIXES = ('.swp', '.tmp', '.pem', '.key')


class BackupError(Exception):
    pass


def _digest_file(src, sink=None):
    digest = hashlib.sha256()
    total = 0
    with src.open('rb') as stream:
        while True:
            chunk = stream.read(65536)
            if not chunk:
                break
            total += len(chunk)
            if total > MAX_FILE_BYTES:
                raise BackupError('File exceeds the 25 MiB safety limit: ' + str(src))
            digest.update(chunk)
            if sink is not None:
                sink.write(chunk)
    return digest.hexdigest(), total


def _safe_member(name):
    if not isinstance(name, str) or '\\' in name or not name.startswith('payload/'):
        return False
    segments = name.split('/')
    return all(p not in ('', '.', '..') for p in segments) and len(segments) >= 3


class BackupService:
    def __init__(self, home=None, storage=None):
        self.home = Path(home or Path.home()).expanduser().absolute()
        xdg_data = Path(os.environ.get('XDG_DATA_HOME', self.home / '.local/share'))
        self.storage = Path(storage or xdg_data / 'midnight-core' / 'backups').expanduser().absolute()
        self.storage.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.storage.chmod(0o700)

    def _destination(self, component):
        if component not in COMPONENTS:
            raise BackupError('Unknown component: ' + str(component))
        return self.home / COMPONENTS[component][1]

    def _validate_component_names(self, components):
        chosen = list(dict.fromkeys(components))
        if not chosen or any(x not in COMPONENTS for x in chosen):
            raise BackupError('Select at least one valid configuration component.')
        return chosen

    def _check_no_symlink_parents(self, target):
        p = target
        while p != self.home and p != p.parent:
            if p.is_symlink():
                raise BackupError('Refusing symlink path: ' + str(p))
            p = p.parent
        if p != self.home:
            raise BackupError('Target is outside your home directory.')

    def _paths_for_component(self, component):
        dest = self._destination(component)
        self._check_no_symlink_parents(dest)
        label, _, kind = COMPONENTS[component]
        if not dest.exists():
            return False, []
        if kind == 'file':
            if not dest.is_file():
                raise BackupError(f'{label} is not a regular file.')
            return True, [(dest, f'payload/{component}/__file__')]
        if not dest.is_dir():
            raise BackupError(f'{label} is not a directory.')
        entries = []
        for root, dirs, files in os.walk(dest, followlinks=False):
            root = Path(root)
            dirs[:] = sorted(d for d in dirs if d not in EXCLUDE_DIRS
                             and not (root / d).is_symlink())
            for filename in sorted(files):
                path = root / filename
                if (filename in EXCLUDE_FILES or filename.endswith(EXCLUDE_SUFFIXES)
                        or path.is_symlink() or not path.is_file()):
                    continue
                rel = path.relative_to(dest).as_posix()
                entries.append((path, f'payload/{component}/{rel}'))
        return True, entries

    def create_backup(self, components, label='manual'):
        """Create user-private ZIP. Returns the backup filename."""
        chosen = self._validate_component_names(components)
        files = []
        present = []
        for comp in chosen:
            exists, entries = self._paths_for_component(comp)
            if exists:
                present.append(comp)
                files.extend((comp, source, member) for source, member in entries)
        if len(files) > MAX_FILES:
            raise BackupError(f'Too many files (limit {MAX_FILES}).')
        total = sum(path.stat().st_size for _, path, _ in files)
        if total > MAX_TOTAL_BYTES or any(p.stat().st_size > MAX_FILE_BYTES for _, p, _ in files):
            raise BackupError('Selected files exceed backup size limits.')
        now = datetime.now(timezone.utc)
        name = f'mc-{now:%Y%m%d-%H%M%S}-{uuid.uuid4().hex[:8]}.zip'
        output = self.storage / name
        fd = os.open(output, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        records = []
        try:
            with os.fdopen(fd, 'wb') as handle, zipfile.ZipFile(
                handle, mode='w', compression=zipfile.ZIP_DEFLATED,
                compresslevel=6, allowZip64=False,
            ) as archive:
                for comp, source, member in files:
                    meta = source.stat()
                    if not stat.S_ISREG(meta.st_mode):
                        raise BackupError('Only regular files are supported.')
                    info = zipfile.ZipInfo(member)
                    info.compress_type = zipfile.ZIP_DEFLATED
                    info.external_attr = (stat.S_IFREG | (meta.st_mode & 0o700)) << 16
                    with archive.open(info, 'w') as writer:
                        sha, size = _digest_file(source, writer)
                    records.append({
                        'component': comp, 'member': member,
                        'size': size, 'sha256': sha,
                        'mode': meta.st_mode & 0o700,
                    })
                manifest = {
                    'version': VERSION, 'created_at': now.isoformat(),
                    'label': str(label)[:50], 'components': chosen,
                    'present': present, 'files': records,
                }
                archive.writestr('manifest.json', json.dumps(manifest, indent=2))
        except Exception:
            output.unlink(missing_ok=True)
            raise
        return name

    def _managed_archive(self, name):
        if not isinstance(name, str) or not name.startswith('mc-') or not name.endswith('.zip') or Path(name).name != name:
            raise BackupError('Invalid managed backup filename.')
        archive = self.storage / name
        if archive.is_symlink() or not archive.is_file():
            raise BackupError('Managed backup not found.')
        return archive

    def _read_manifest(self, zf):
        names = zf.namelist()
        if len(names) != len(set(names)) or len(names) > MAX_FILES + 1:
            raise BackupError('Duplicate entries or excessive file count.')
        try:
            info = zf.getinfo('manifest.json')
            if info.file_size > 1_000_000:
                raise BackupError('Manifest is too large.')
            manifest = json.loads(zf.read(info))
        except (KeyError, ValueError) as exc:
            raise BackupError('Missing or invalid backup manifest.') from exc
        if not isinstance(manifest, dict) or manifest.get('version') != VERSION:
            raise BackupError('Unsupported backup format.')
        components = manifest.get('components')
        present = manifest.get('present')
        entries = manifest.get('files')
        if not isinstance(components, list) or not isinstance(present, list) or not isinstance(entries, list):
            raise BackupError('Invalid manifest structure.')
        self._validate_component_names(components)
        if len(components) != len(set(components)) or any(p not in components for p in present) or len(present) != len(set(present)):
            raise BackupError('Invalid component membership.')
        expected = {'manifest.json'}
        total = 0
        for e in entries:
            if not isinstance(e, dict):
                raise BackupError('Invalid file record.')
            key = e.get('component')
            member = e.get('member')
            size = e.get('size')
            sha = e.get('sha256')
            mode = e.get('mode')
            if (key not in present or not _safe_member(member)
                    or not member.startswith(f'payload/{key}/')
                    or not isinstance(size, int) or not 0 <= size <= MAX_FILE_BYTES
                    or not isinstance(mode, int) or not 0 <= mode <= 0o700
                    or not isinstance(sha, str) or len(sha) != 64
                    or any(ch not in '0123456789abcdef' for ch in sha)):
                raise BackupError('Unsafe or invalid archive record.')
            suffix = member[len(f'payload/{key}/'):]
            if COMPONENTS[key][2] == 'file' and suffix != '__file__':
                raise BackupError('Invalid path for single-file component.')
            if COMPONENTS[key][2] == 'dir':
                parts = PurePosixPath(suffix).parts
                if (any(part in EXCLUDE_DIRS for part in parts[:-1])
                        or parts[-1] in EXCLUDE_FILES
                        or parts[-1].endswith(EXCLUDE_SUFFIXES)):
                    raise BackupError('Archive contains an excluded config path.')
            if member in expected:
                raise BackupError('Repeated file entry.')
            expected.add(member)
            try:
                item_info = zf.getinfo(member)
            except KeyError as exc:
                raise BackupError('Missing archive member.') from exc
            if item_info.is_dir() or item_info.file_size != size:
                raise BackupError('Invalid archive file metadata.')
            archive_mode = item_info.external_attr >> 16
            if stat.S_ISLNK(archive_mode):
                raise BackupError('Symlinks are not supported in backups.')
            total += size
            if total > MAX_TOTAL_BYTES:
                raise BackupError('Archive exceeds total safety limit.')
        if expected != set(names):
            raise BackupError('Unexpected entries in archive.')
        return manifest

    def _validate_bytes(self, zf, record, output=None):
        digest = hashlib.sha256()
        total = 0
        with zf.open(record['member'], 'r') as reader:
            while True:
                part = reader.read(65536)
                if not part:
                    break
                total += len(part)
                if total > record['size'] or total > MAX_FILE_BYTES:
                    raise BackupError('Member exceeded expected file size.')
                digest.update(part)
                if output is not None:
                    output.write(part)
        if total != record['size'] or digest.hexdigest() != record['sha256']:
            raise BackupError('Backup checksum mismatch: ' + record['member'])

    def inspect(self, name):
        path = self._managed_archive(name)
        try:
            with zipfile.ZipFile(path, 'r') as zf:
                manifest = self._read_manifest(zf)
                for entry in manifest['files']:
                    self._validate_bytes(zf, entry)
            return manifest
        except (OSError, zipfile.BadZipFile, EOFError, RuntimeError) as exc:
            raise BackupError('Could not verify archive: ' + str(exc)) from exc

    def list_backups(self):
        records = []
        for path in sorted(self.storage.glob('mc-*.zip'), reverse=True):
            if path.is_symlink() or not path.is_file():
                continue
            records.append({'name': path.name, 'size': path.stat().st_size})
        return records

    def restore(self, name, components):
        """Verify and overlay saved files; keep unrelated files (e.g. .git).

        Before writing, save a rescue archive of the current selected components.
        If a write fails, roll back any files already replaced.
        """
        chosen = self._validate_component_names(components)
        archive_path = self._managed_archive(name)
        manifest = self.inspect(name)
        if any(c not in manifest['present'] for c in chosen):
            raise BackupError('Selected components must exist in this archive.')
        records = [e for e in manifest['files'] if e['component'] in chosen]

        def target_for(record):
            key = record['component']
            target = self._destination(key)
            if COMPONENTS[key][2] == 'dir':
                relative = record['member'][len(f'payload/{key}/'):]
                target = target / PurePosixPath(relative)
            self._check_no_symlink_parents(target)
            if target.exists() and not target.is_file():
                raise BackupError('Cannot overwrite non-file path: ' + str(target))
            return target

        for record in records:
            target_for(record)  # Validate all destinations before any replacement.

        # Stage and verify the complete selected archive subset before touching settings.
        with tempfile.TemporaryDirectory(prefix='.stage-', dir=self.storage) as tmp:
            workspace = Path(tmp)
            incoming = workspace / 'incoming'
            incoming.mkdir()
            with zipfile.ZipFile(archive_path, 'r') as zf:
                for record in records:
                    stage = incoming / record['member']
                    stage.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with stage.open('xb') as output:
                        self._validate_bytes(zf, record, output)
                    stage.chmod(0o600 | (record['mode'] & 0o100))

            # User-private rescue of current files, retained even on failure.
            rescue_name = self.create_backup(chosen, label='pre-restore')
            rollback_dir = workspace / 'previous'
            rollback_dir.mkdir()
            touched = []
            try:
                for record in records:
                    target = target_for(record)
                    stage = incoming / record['member']
                    previous = rollback_dir / record['member']
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    old_exists = target.exists()
                    item = {'target': target, 'previous': previous,
                            'old_moved': False, 'new_moved': False}
                    touched.append(item)
                    if old_exists:
                        previous.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                        shutil.move(str(target), str(previous))
                        item['old_moved'] = True
                    shutil.move(str(stage), str(target))
                    item['new_moved'] = True
            except Exception as error:
                problems = []
                for item in reversed(touched):
                    target = item['target']
                    try:
                        if item['old_moved'] or item['new_moved']:
                            if target.exists() or target.is_symlink():
                                target.unlink()
                        if item['old_moved']:
                            shutil.move(str(item['previous']), str(target))
                    except Exception as rollback_error:
                        problems.append(str(rollback_error))
                if problems:
                    raise BackupError('Restore failed and rollback had problems. Rescue: '
                                      + rescue_name + '; ' + '; '.join(problems)) from error
                raise BackupError('Restore failed; previous files were rolled back. Rescue: '
                                  + rescue_name) from error
        return rescue_name
