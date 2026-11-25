# Midnight Core v1.0.0 — Manual Fedora 45 test plan

Run on the actual Fedora GNOME/Wayland desktop **without sudo**. Automated syntax and unit tests do not replace this checklist.

## Preparation

- [ ] Close older running Control Center instances and reopen the development project (`/usr/bin/python3 main.py`).
- [ ] Confirm you have current backups, especially `~/.config/midnight-core-backup` and managed backup archives.
- [ ] Verify `python3 -m unittest discover -s tests -v` and `python3 -m unittest discover -s packaging/tests -v` pass if those test folders exist.
- [ ] Run `python3 scripts/release_suite.py check --project .`; review `dist/QA_REPORT.md`.
- [ ] Check `git diff`, `git diff --cached`, `git status --short`, including commit history for previously committed secrets.

## Visual/navigation smoke test

- [ ] App starts and closes without Python exceptions or crashes.
- [ ] Sidebar shows all 11 pages; each opens successfully and returns to Overview.
- [ ] Layout remains readable at normal window size and after resizing to 760×520.
- [ ] Search, keyboard focus and scrolling work in long pages.
- [ ] No text, controls or logs are clipped; fonts/colors remain readable.

## Functional smoke test

- [ ] Overview: actual CPU/RAM/disk and uptime visible; refresh updates; battery missing gracefully.
- [ ] Appearance: current values load; apply a harmless change; restore exact previous values.
- [ ] Lock Screen: reads V3 settings; change a minor preference and restore; lock-screen effect confirmed only after saving and locking. **Do not use this to reset the extension.**
- [ ] Boot & Login: read Plymouth theme and GDM status. **Do not change Plymouth on release smoke test unless you have recovery media and a tested rollback path.** GDM remains read-only.
- [ ] Terminal: Alacritty and Starship values displayed; no unrelated TOML keys lost. Test with a small reversible setting.
- [ ] Neovim IDE: reads settings; external tools open correctly; preserve customized theme and keymaps.
- [ ] Extensions: list loads, preferences open; only enable/disable nonessential extensions if testing is needed.
- [ ] Aliases: add benign alias (`echo TEST`), source new shell, run it, delete it; original aliases unchanged.
- [ ] Performance: CPU/memory/processes update; diagnostics do not freeze UI; journal permission errors are explained.
- [ ] Backup & Restore: create backup; Verify & Preview reports integrity. Restore **only a disposable test setting**, verify it, and keep rescue backup.
- [ ] Installed desktop app starts via `gtk-launch io.midnightcore.ControlCenter` after the Stage 11 installer has been re-run from the current project.

## Release decision

- [ ] Automated checks exit 0.
- [ ] No unresolved high-impact issues.
- [ ] No secrets or personal paths in published files or Git history.
- [ ] Review final archive file list and checksum.
- [ ] Choose a software license, or clearly state source-available without an open-source license.
- [ ] Version, screenshots and documentation match the tested state.

**If any item fails: do not tag `v1.0.0` as stable.** Fix and rerun. A GitHub prerelease is an option for tested-but-incomplete builds.
