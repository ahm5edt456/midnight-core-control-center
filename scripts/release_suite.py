#!/usr/bin/env python3
"""Midnight Core release preflight and safe source-bundle builder.

Read-only audit by default. Never uploads, tags, commits, installs or modifies
Fedora settings. Build only writes under project/dist/.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile

APP_ID = "io.midnightcore.ControlCenter"
VERSION = "1.0.0"
MAX_FILE = 12 * 1024 * 1024
MAX_TOTAL = 60 * 1024 * 1024
ALLOWED_ASSETS = {".css", ".svg", ".png", ".jpg", ".jpeg", ".webp", ".ui", ".json", ".gresource"}
ALLOWED_PACKAGE = {".py", ".sh", ".svg", ".md", ".desktop"}
FORBIDDEN_SUFFIXES = {".pem", ".key", ".p12", ".pfx", ".db", ".sqlite", ".sqlite3", ".zip", ".gz", ".tar", ".tgz"}
FORBIDDEN_NAMES = {".env", ".env.local", ".env.production", ".env.development", "id_rsa", "id_ed25519", "credentials.json", "secrets.json", "known_hosts"}
SENSITIVE_CONTENT = [
    ("private-key header", re.compile(r"(?m)^-----BEGIN (?:[A-Z ]+ )?PRIVATE KEY-----")),
    ("GitHub access token", re.compile("ghp" + r"_[A-Za-z0-9]{30,}")),
    ("GitHub fine-grained token", re.compile("github" + r"_pat_[A-Za-z0-9_]{40,}")),
    ("AWS access key", re.compile(r"\b(?:AKIA|ASIA)[A-Z0-9]{16}\b")),
    ("GitLab access token", re.compile("glpat" + r"-[A-Za-z0-9_-]{16,}")),
    ("Stripe live key", re.compile("sk" + r"_live_[A-Za-z0-9]{12,}")),
]


def project_files(root: Path):
    """Explicit release allowlist; do not include arbitrary home or git files."""
    files = []
    for rel in ("main.py", "README.md", "LICENSE", "LICENSE.md", ".gitignore", "requirements.txt"):
        p = root / rel
        if p.is_file() or p.is_symlink():
            files.append(p)
    folders = [
        ("midnight", {".py"}),
        ("assets", ALLOWED_ASSETS),
        ("packaging", ALLOWED_PACKAGE),
        ("scripts", {".py", ".sh"}),
        ("docs", {".md"}),
        ("tests", {".py"}),
        (".github/workflows", {".yml", ".yaml"}),
    ]
    for dirname, suffixes in folders:
        base = root / dirname
        if not base.exists() and not base.is_symlink():
            continue
        if base.is_symlink():
            files.append(base)
            continue
        for parent, dirs, names in os.walk(base, followlinks=False):
            dirs[:] = [d for d in dirs if d not in {"__pycache__", ".git", ".venv", "node_modules", ".cache"} and not d.startswith(".")]
            for name in names:
                file = Path(parent) / name
                if file.suffix.lower() in suffixes and not name.startswith("."):
                    files.append(file)
    return sorted(set(files), key=lambda p: str(p.relative_to(root)))


def git_tracked(root: Path):
    result = subprocess.run(["git", "ls-files", "--cached", "-z"], cwd=root, capture_output=True, check=False)
    if result.returncode:
        return None
    return [root / os.fsdecode(raw) for raw in result.stdout.split(b"\0") if raw]


def bad_filename(relative: Path):
    parts = relative.parts
    name = relative.name.lower()
    return (name in FORBIDDEN_NAMES or name.endswith(".env") or
            name.startswith(".env.") or relative.suffix.lower() in FORBIDDEN_SUFFIXES or
            any(x in {".ssh", ".gnupg", ".venv", "__pycache__"} for x in parts))


def run_unit_tests(root: Path):
    results = []
    for folder in ("tests", "packaging/tests"):
        if not (root / folder).is_dir():
            continue
        if not list((root / folder).rglob("test_*.py")):
            continue
        cmd = [sys.executable, "-m", "unittest", "discover", "-s", folder, "-p", "test_*.py", "-v"]
        try:
            result = subprocess.run(cmd, cwd=root, capture_output=True, text=True, timeout=120, check=False)
            log = (result.stdout + "\n" + result.stderr)[-6000:]
            results.append((folder, result.returncode == 0, log))
        except subprocess.TimeoutExpired:
            results.append((folder, False, "Timed out after 120s"))
    return results


def audit(root: Path, run_tests=True):
    errors, warnings, passed = [], [], []
    required = ["main.py", "midnight/application.py", "midnight/window.py", "assets/style.css"]
    for rel in required:
        if not (root / rel).is_file():
            errors.append(f"Missing required file: {rel}")
    files = project_files(root)
    paths = {str(p.relative_to(root)) for p in files}
    for p in files:
        rel = p.relative_to(root)
        if p.is_symlink():
            errors.append(f"Symlink is not allowed in release: {rel}")
            continue
        if not p.is_file():
            errors.append(f"Not a regular file: {rel}")
            continue
        if bad_filename(rel):
            errors.append(f"Sensitive filename in release: {rel}")
        if p.stat().st_size > MAX_FILE:
            errors.append(f"File too large for release: {rel}")
        if p.suffix == ".py":
            try:
                tree = ast.parse(p.read_text(encoding="utf-8-sig"), filename=str(rel))
            except (SyntaxError, UnicodeError, OSError) as exc:
                errors.append(f"Python parse failed: {rel}: {type(exc).__name__}: {exc}")
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom) and node.module and node.module.startswith("midnight."):
                    target = node.module.replace(".", "/")
                    if not (root / (target + ".py")).is_file() and not (root / target / "__init__.py").is_file():
                        errors.append(f"Missing Python module imported by {rel}: {node.module}")
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr == "format_secondary_text":
                    errors.append(f"Deprecated GTK dialog call in {rel}, line {node.lineno}")
    app = root / "midnight/application.py"
    if app.is_file() and APP_ID not in app.read_text(encoding="utf-8", errors="replace"):
        errors.append("Application ID mismatch in midnight/application.py")
    tracked = git_tracked(root)
    if tracked is None:
        warnings.append("Git repository is absent or inaccessible; tracked-file scan skipped")
    else:
        passed.append(f"Git tracked files examined: {len(tracked)}")
    scan_files = set(files) | set(tracked or [])
    for p in sorted(scan_files):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if bad_filename(rel):
            errors.append(f"Sensitive tracked/release filename: {rel}")
        if p.is_symlink():
            errors.append(f"Symlink found in tracked/release file: {rel}")
            continue
        if not p.is_file() or p.stat().st_size > 2 * 1024 * 1024:
            continue
        try:
            content = p.read_text(encoding="utf-8")
        except (UnicodeError, OSError):
            continue
        for label, pattern in SENSITIVE_CONTENT:
            match = pattern.search(content)
            if match:
                errors.append(f"Possible {label} in {rel}, line {content.count(chr(10), 0, match.start())+1} (value hidden)")
    if not (root / "LICENSE").is_file() and not (root / "LICENSE.md").is_file():
        warnings.append("LICENSE is missing: choose an explicit license before calling the project open-source")
    if not (root / "packaging/packager.py").is_file():
        warnings.append("Stage 11 packager.py not found: GNOME install packaging cannot be verified")
    if not (root / "docs/TEST_PLAN.md").is_file():
        warnings.append("Manual test plan is missing")
    if (root / ".git").exists():
        status = subprocess.run(["git", "status", "--porcelain"], cwd=root, capture_output=True, text=True, check=False)
        if status.returncode == 0 and status.stdout.strip():
            warnings.append("Working tree is not clean; commit and review changes before tagging")
    desktop = Path.home() / ".local/share/applications" / (APP_ID + ".desktop")
    validate = shutil.which("desktop-file-validate")
    if desktop.exists() and validate:
        result = subprocess.run([validate, str(desktop)], capture_output=True, text=True, timeout=15, check=False)
        if result.returncode:
            errors.append("Installed .desktop validation failed: " + (result.stderr or result.stdout).strip()[:300])
        else:
            passed.append("Installed .desktop file validated")
    else:
        warnings.append("Desktop entry check skipped (not installed or desktop-file-validate missing)")
    test_logs = []
    if run_tests:
        tests = run_unit_tests(root)
        if not tests:
            warnings.append("No project unit tests found under tests/ or packaging/tests/")
        for folder, ok, log in tests:
            test_logs.append({"folder": folder, "passed": ok, "output": log})
            if ok:
                passed.append(f"Unit tests passed: {folder}")
            else:
                errors.append(f"Unit tests failed: {folder} (see report output)")
    passed.append(f"Release source files inspected: {len(files)}")
    return {"project": str(root), "version": VERSION, "passed": passed,
            "warnings": sorted(set(warnings)), "errors": sorted(set(errors)), "tests": test_logs,
            "included_paths": sorted(paths)}


def make_report(data, root):
    out = root / "dist"
    out.mkdir(parents=True, exist_ok=True)
    report = out / "QA_REPORT.md"
    report.write_text("# Midnight Core — Release preflight\n\n" +
        f"Version: {data['version']}  \nAutomated outcome: **{'FAIL' if data['errors'] else 'PASS (manual GUI verification required)'}**\n\n" +
        "## Errors\n" + ("\n".join("- " + x for x in data["errors"]) or "- None") + "\n\n" +
        "## Warnings\n" + ("\n".join("- " + x for x in data["warnings"]) or "- None") + "\n\n" +
        "## Checks passed\n" + ("\n".join("- " + x for x in data["passed"]) or "- None") + "\n\n" +
        "## Automated unit test logs\n" + "\n".join(f"### {t['folder']}\n```\n{t['output']}\n```\n" for t in data['tests']) +
        "\n**This does not certify GTK runtime, real GNOME integration, boot/login changes, or release readiness.**\n",
        encoding="utf-8")
    return report


def build_bundle(root: Path, data):
    if data["errors"]:
        raise RuntimeError("Preflight has errors. Fix them before building a release ZIP.")
    sources = project_files(root)
    if not sources:
        raise RuntimeError("Empty project source list")
    total = sum(p.stat().st_size for p in sources)
    if total > MAX_TOTAL:
        raise RuntimeError("Source archive exceeds 60 MiB policy")
    dist = root / "dist"
    dist.mkdir(parents=True, exist_ok=True)
    basename = f"midnight-core-control-center-v{VERSION}-source"
    output = dist / (basename + ".zip")
    manifest = {}
    fd, tempname = tempfile.mkstemp(prefix=".midnight-release-", suffix=".zip", dir=dist)
    os.close(fd)
    try:
        with zipfile.ZipFile(tempname, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=8) as archive:
            for p in sources:
                rel = p.relative_to(root).as_posix()
                contents = p.read_bytes()
                manifest[rel] = hashlib.sha256(contents).hexdigest()
                archive.writestr(f"{basename}/{rel}", contents)
            meta = json.dumps({"name": "Midnight Core Control Center", "version": VERSION,
                               "sha256": manifest}, indent=2, sort_keys=True) + "\n"
            archive.writestr(f"{basename}/SOURCE_MANIFEST.json", meta.encode("utf-8"))
        with zipfile.ZipFile(tempname) as archive:
            if archive.testzip() is not None:
                raise RuntimeError("ZIP internal integrity check failed")
        os.replace(tempname, output)
    finally:
        if os.path.exists(tempname):
            os.unlink(tempname)
    digest = hashlib.sha256(output.read_bytes()).hexdigest()
    checksum = dist / (output.name + ".sha256")
    checksum.write_text(f"{digest}  {output.name}\n", encoding="utf-8")
    return output, checksum, len(sources)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=("check", "build"))
    parser.add_argument("--project", type=Path, default=Path.cwd())
    parser.add_argument("--skip-tests", action="store_true", help="Only for initial inspection; not final release validation")
    args = parser.parse_args(argv)
    root = args.project.expanduser().resolve()
    if not root.is_dir():
        parser.error("Project folder not found")
    result = audit(root, run_tests=not args.skip_tests)
    report = make_report(result, root)
    for msg in result["passed"]:
        print("PASS:", msg)
    for msg in result["warnings"]:
        print("WARN:", msg)
    for msg in result["errors"]:
        print("FAIL:", msg)
    print("Report:", report)
    if result["errors"]:
        return 1
    if args.command == "build":
        output, checksum, count = build_bundle(root, result)
        print(f"Release source: {output} ({count} files)")
        print("SHA256 file:", checksum)
    print("Automated checks passed. Manual GNOME GUI testing remains required.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
