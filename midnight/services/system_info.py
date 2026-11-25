import os
import platform
import subprocess
from pathlib import Path


def read_text(path, default=""):
    try:
        return Path(path).read_text().strip()
    except (OSError, UnicodeError):
        return default


def gib(value):
    return value / (1024 ** 3)


def cpu_counters():
    try:
        line = read_text("/proc/stat").splitlines()[0]
        values = list(map(int, line.split()[1:9]))

        total = sum(values)
        idle = values[3] + values[4]

        return total, idle
    except (ValueError, IndexError):
        return None


def memory_usage():
    try:
        data = {}

        for line in read_text("/proc/meminfo").splitlines():
            key, value = line.split(":", 1)
            data[key] = int(value.strip().split()[0])

        total = data["MemTotal"] * 1024
        available = data["MemAvailable"] * 1024
        used = max(0, total - available)

        return used, total
    except (ValueError, KeyError, IndexError):
        return None


def disk_usage():
    try:
        disk = os.statvfs(Path.home())

        total = disk.f_blocks * disk.f_frsize
        used = (disk.f_blocks - disk.f_bfree) * disk.f_frsize

        return used, total
    except OSError:
        return None


def battery_info():
    base = Path("/sys/class/power_supply")

    for battery in sorted(base.glob("BAT*")):
        capacity = read_text(battery / "capacity")
        status = read_text(battery / "status", "Unknown")

        try:
            percent = max(0, min(100, int(capacity)))
            return percent, status
        except ValueError:
            continue

    return None


def uptime_text():
    try:
        seconds = int(float(
            read_text("/proc/uptime").split()[0]
        ))
    except (ValueError, IndexError):
        return "Unavailable"

    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes = remainder // 60

    if days:
        return f"{days}d {hours}h {minutes}m"

    return f"{hours}h {minutes}m"


def cpu_model():
    for line in read_text("/proc/cpuinfo").splitlines():
        if line.startswith("model name"):
            return line.split(":", 1)[1].strip()

    return platform.processor() or "Unavailable"


def gpu_models():
    try:
        result = subprocess.run(
            ["lspci"],
            capture_output=True,
            text=True,
            timeout=3,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return "Unavailable"

    devices = []

    for line in result.stdout.splitlines():
        if any(kind in line.lower() for kind in (
            "vga compatible controller",
            "3d controller",
            "display controller",
        )):
            devices.append(line.split(": ", 1)[-1])

    return " | ".join(devices) if devices else "Unavailable"


def system_details():
    try:
        os_name = platform.freedesktop_os_release().get(
            "PRETTY_NAME", "Linux"
        )
    except (OSError, AttributeError):
        os_name = "Linux"

    return {
        "Operating System": os_name,
        "Kernel": platform.release(),
        "Desktop": os.environ.get(
            "XDG_CURRENT_DESKTOP", "Unavailable"
        ),
        "Session": os.environ.get(
            "XDG_SESSION_TYPE", "Unavailable"
        ),
        "Processor": cpu_model(),
        "Graphics": gpu_models(),
    }


class SystemMonitor:

    def __init__(self):
        self.previous_cpu = cpu_counters()

    def cpu_usage(self):
        current = cpu_counters()
        previous = self.previous_cpu
        self.previous_cpu = current

        if current is None or previous is None:
            return None

        total_delta = current[0] - previous[0]
        idle_delta = current[1] - previous[1]

        if total_delta <= 0:
            return None

        return max(
            0.0,
            min(100.0, 100 * (1 - idle_delta / total_delta))
        )

    def snapshot(self):
        return {
            "cpu": self.cpu_usage(),
            "memory": memory_usage(),
            "disk": disk_usage(),
            "battery": battery_info(),
            "uptime": uptime_text(),
        }
