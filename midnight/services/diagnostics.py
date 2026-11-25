"""Read-only Fedora diagnostics for Midnight Core Control Center.

All subprocess calls are bounded, use argument arrays, and never elevate privileges.
"""

from __future__ import annotations

import os
from pathlib import Path
import re
import shutil
import subprocess
import threading


class DiagnosticError(RuntimeError):
    pass


def run_readonly(argv: list[str], timeout: float = 4.0, limit: int = 16000) -> tuple[int, str]:
    if not argv or not shutil.which(argv[0]):
        return 127, f"{argv[0] if argv else 'Command'} is not installed."
    env = os.environ.copy()
    env.update({"PAGER": "cat", "SYSTEMD_PAGER": "cat", "SYSTEMD_COLORS": "0", "NO_COLOR": "1"})
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, errors='replace',
                              timeout=timeout, check=False, env=env)
    except subprocess.TimeoutExpired:
        return 124, f"Timed out after {timeout:g} seconds."
    except OSError as exc:
        return 125, f"Unable to execute {argv[0]}: {exc}"
    content = (proc.stdout or '').strip()
    if proc.returncode and not content:
        content = (proc.stderr or '').strip()
    # Never allow the diagnostics panel to grow unbounded.
    return proc.returncode, content[:limit] or '(No output)'


def percent(used: int, total: int) -> float | None:
    return round(max(0, min(100, used / total * 100)), 1) if total > 0 else None


def _cpu_counters() -> tuple[int, int] | None:
    try:
        values = [int(v) for v in Path('/proc/stat').read_text().splitlines()[0].split()[1:]]
        idle = values[3] + values[4]
        return sum(values), idle
    except (OSError, ValueError, IndexError):
        return None


def _memory() -> tuple[int, int] | None:
    try:
        fields = {}
        for line in Path('/proc/meminfo').read_text().splitlines():
            name, val = line.split(':', 1)
            fields[name] = int(val.strip().split()[0]) * 1024
        total = fields['MemTotal']
        available = fields['MemAvailable']
        return max(0, total - available), total
    except (OSError, KeyError, ValueError, IndexError):
        return None


def _storage() -> tuple[int, int] | None:
    try:
        data = os.statvfs(Path.home())
        total = data.f_blocks * data.f_frsize
        used = (data.f_blocks - data.f_bfree) * data.f_frsize
        return used, total
    except OSError:
        return None


def _gib(value: int) -> str:
    return f'{value / 1024**3:.1f} GiB'


def _gpu_utilization() -> tuple[float | None, str]:
    # NVIDIA GPUs only; do not misrepresent GPU usage on Intel/AMD devices.
    if not shutil.which('nvidia-smi'):
        return None, 'Utilization requires a supported GPU tool'
    code, output = run_readonly(
        ['nvidia-smi', '--query-gpu=utilization.gpu', '--format=csv,noheader,nounits'], timeout=3,
    )
    if code:
        return None, 'GPU utilization unavailable'
    try:
        value = float(output.splitlines()[0].strip())
        if 0 <= value <= 100:
            return value, 'NVIDIA GPU utilization'
    except (ValueError, IndexError):
        pass
    return None, 'GPU utilization unavailable'


class DiagnosticsService:
    def __init__(self):
        self._last_cpu = None
        self._lock = threading.Lock()

    def live(self) -> dict:
        with self._lock:
            present = _cpu_counters()
            old = self._last_cpu
            self._last_cpu = present
        cpu = None
        if present and old:
            delta = present[0] - old[0]
            idle = present[1] - old[1]
            if delta > 0:
                cpu = round(max(0, min(100, 100 * (1 - idle / delta))), 1)

        mem = _memory()
        disk = _storage()
        gpu, gpu_detail = _gpu_utilization()
        try:
            load = os.getloadavg()
            load_description = ' / '.join(f'{item:.2f}' for item in load)
        except OSError:
            load_description = 'Unavailable'
        return {
            'cpu': {'value': cpu, 'detail': 'System CPU utilization' if cpu is not None else 'Measuring CPU…'},
            'memory': {'value': percent(*mem) if mem else None,
                       'detail': f'{_gib(mem[0])} of {_gib(mem[1])} used' if mem else 'Unavailable'},
            'disk': {'value': percent(*disk) if disk else None,
                     'detail': f'{_gib(disk[0])} of {_gib(disk[1])} used (home filesystem)' if disk else 'Unavailable'},
            'gpu': {'value': gpu, 'detail': gpu_detail},
            'load': load_description,
        }

    def processes(self, limit=10) -> list[dict]:
        code, output = run_readonly(['ps', '-eo', 'pid=,comm=,%cpu=,rss=', '--sort=-%cpu'], timeout=4, limit=26000)
        if code:
            raise DiagnosticError(output)
        records = []
        for line in output.splitlines():
            values = line.strip().split()
            if len(values) != 4:
                continue
            try:
                pid, name, cpu, rss = values
                records.append({'pid': int(pid), 'name': name[:60],
                                'cpu': float(cpu), 'memory_mib': round(int(rss) / 1024, 1)})
            except ValueError:
                continue
            if len(records) >= max(1, min(50, limit)):
                break
        return records

    def services(self) -> dict:
        _, failed = run_readonly(
            ['systemctl', '--user', '--failed', '--no-pager', '--no-legend', '--plain'], timeout=4, limit=2500)
        statuses = {}
        for name in ('gdm.service', 'NetworkManager.service', 'docker.service'):
            code, output = run_readonly(['systemctl', 'is-active', name], timeout=3, limit=160)
            statuses[name.removesuffix('.service')] = output if code in (0, 3, 4) else 'Unavailable'
        return {'failed_user_units': failed, 'system': statuses}

    def checks(self) -> list[dict]:
        checks = [
            ('GNOME', 'gnome-shell', ['gnome-shell', '--version']),
            ('Neovim', 'nvim', ['nvim', '--version']),
            ('Docker CLI', 'docker', ['docker', '--version']),
            ('Git', 'git', ['git', '--version']),
            ('Python', 'python3', ['python3', '--version']),
            ('Alacritty', 'alacritty', ['alacritty', '--version']),
            ('Starship', 'starship', ['starship', '--version']),
        ]
        result = []
        for label, executable, argv in checks:
            if shutil.which(executable) is None:
                result.append({'name': label, 'status': 'Missing', 'details': 'Executable not found'})
                continue
            code, output = run_readonly(argv, timeout=3, limit=180)
            result.append({'name': label, 'status': 'Available' if code == 0 else 'Check failed',
                           'details': output.splitlines()[0] if output else 'No version reported'})
        return result

    def log(self, source='user') -> str:
        if source not in ('user', 'boot'):
            raise ValueError('Unknown log source')
        args = ['journalctl', '--boot', '--priority=err', '--lines=35',
                '--no-pager', '--output=short-iso']
        if source == 'user':
            args.insert(1, '--user')
        code, output = run_readonly(args, timeout=6, limit=14000)
        if code:
            return 'Journal unavailable for this user: ' + output
        return output
