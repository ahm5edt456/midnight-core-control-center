"""Read-only snapshot of developer tools, local Git project and Docker containers."""
from pathlib import Path
import shutil
import subprocess


TOOLS = (
    ("git", "Git", ["git", "--version"]),
    ("gh", "GitHub CLI", ["gh", "--version"]),
    ("lazygit", "LazyGit", ["lazygit", "--version"]),
    ("docker", "Docker", ["docker", "--version"]),
    ("nvim", "Neovim", ["nvim", "--version"]),
    ("python3", "Python", ["python3", "--version"]),
    ("uv", "UV", ["uv", "--version"]),
    ("gcc", "GCC", ["gcc", "--version"]),
    ("g++", "G++", ["g++", "--version"]),
    ("clang", "Clang", ["clang", "--version"]),
    ("make", "Make", ["make", "--version"]),
    ("cmake", "CMake", ["cmake", "--version"]),
    ("node", "Node.js", ["node", "--version"]),
    ("tmux", "Tmux", ["tmux", "-V"]),
    ("alacritty", "Alacritty", ["alacritty", "--version"]),
    ("starship", "Starship", ["starship", "--version"]),
    ("valgrind", "Valgrind", ["valgrind", "--version"]),
)


def command(argv, cwd=None, timeout=3):
    """No shell, no writes, bounded output and timeout."""
    try:
        proc = subprocess.run(
            argv,
            cwd=str(cwd) if cwd else None,
            capture_output=True,
            text=True,
            errors="replace",
            timeout=timeout,
            check=False,
        )
        output = (proc.stdout or proc.stderr).strip()
        return proc.returncode, output[:1000]
    except (OSError, subprocess.TimeoutExpired) as error:
        return -1, str(error)[:250]


class DeveloperToolsService:
    def __init__(self, project=None, runner=None, finder=None):
        default_repo = Path.home() / "Projects/midnight-core-control-center"
        self.project = Path(project or (default_repo if default_repo.is_dir() else Path(__file__).resolve().parents[2]))
        self.run = runner or command
        self.find = finder or shutil.which

    def tools(self):
        items = []
        for executable, title, argv in TOOLS:
            path = self.find(executable)
            if not path:
                items.append({"name": title, "installed": False, "version": "Not installed"})
                continue
            code, output = self.run(argv, timeout=3)
            version = (output.splitlines()[0] if output else "Version unavailable")[:95]
            items.append({"name": title, "installed": True, "version": version if code == 0 else "Installed · version unavailable"})
        return items

    def git(self):
        if not self.find("git"):
            return {"state": "Git not installed", "detail": "", "branch": "—"}
        code, root = self.run(["git", "rev-parse", "--show-toplevel"], cwd=self.project, timeout=3)
        if code:
            return {"state": "Not a Git repository", "detail": str(self.project), "branch": "—"}
        code, branch = self.run(["git", "branch", "--show-current"], cwd=self.project, timeout=3)
        if code or not branch:
            branch = "Detached HEAD / no branch"
        code, status = self.run(["git", "status", "--porcelain=v1", "-uno"], cwd=self.project, timeout=4)
        state = "Status unavailable" if code else ("Modified files" if status.strip() else "Clean working tree")
        return {"state": state, "detail": root.splitlines()[0], "branch": branch.splitlines()[0]}

    def docker(self):
        if not self.find("docker"):
            return {"state": "Docker not installed", "containers": []}
        code, output = self.run(["docker", "ps", "--format", "{{.Names}}\t{{.Status}}\t{{.Image}}"], timeout=4)
        if code:
            first = output.splitlines()[0] if output else "Docker daemon unavailable"
            return {"state": "Docker unavailable: " + first[:160], "containers": []}
        containers = []
        for line in output.splitlines()[:12]:
            parts = line.split("\t")
            if len(parts) == 3:
                containers.append({"name": parts[0][:70], "status": parts[1][:90], "image": parts[2][:90]})
        return {"state": f"{len(containers)} shown running containers" + (" (max 12)" if len(containers) == 12 else ""), "containers": containers}

    def snapshot(self):
        return {"tools": self.tools(), "git": self.git(), "docker": self.docker()}
