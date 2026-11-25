# Midnight Core Control Center — Stage 11

**Application Packaging** for Fedora GNOME. Installs the Python + GTK4 Control Center in the user's account without requiring root, without modifying the original Git project, and without touching configuration or backup archives.

## Install

Close any running Midnight Core window, then:

```bash
unzip -q -o ~/Downloads/midnight-stage11.zip -d /tmp
cat /tmp/midnight-stage11/install.sh
bash /tmp/midnight-stage11/install.sh
```

The default project source is `~/Projects/midnight-core-control-center`. For a different directory, pass it as an argument:

```bash
bash /tmp/midnight-stage11/install.sh /path/to/project
```

The script validates the files and application ID, checks Python syntax, and then copies **only** `main.py`, Python source under `midnight/`, and static assets under `assets/`. It excludes `.git`, `__pycache__`, `.venv`, backups, project data, and source files unrelated to running the app. It does not run any Git or system-level installation command.

## Installed files

- `~/.local/share/midnight-core-control-center/app/` — runtime snapshot
- `~/.local/bin/midnight-control-center` — direct launcher
- `~/.local/share/applications/io.midnightcore.ControlCenter.desktop` — GNOME launcher
- `~/.local/share/icons/hicolor/scalable/apps/io.midnightcore.ControlCenter.svg` — icon

If `XDG_DATA_HOME` or `XDG_BIN_HOME` are explicitly set, the installer respects them. No special Python virtual environment is used: the app uses `/usr/bin/python3` and your previously installed Fedora GTK4/Libadwaita/PyGObject packages.

## Open

Search for **Midnight Core Control Center** from the GNOME application grid, or execute:

```bash
~/.local/bin/midnight-control-center
# or
gtk-launch io.midnightcore.ControlCenter
```

The older Bash alias `midnight` from previous stages is **not** changed; it may still open your **development source** rather than the installed app. That is intentional to preserve existing aliases. If GNOME keeps focusing an older running instance, close it and open the installed version again.

## Upgrade

Run the same install script after editing the original project. Installation is repeatable; it replaces the installed runtime snapshot and the three files it owns. If installation fails, it attempts to restore the previously installed version and launcher assets. The source project remains unchanged.

## Uninstall

```bash
bash /tmp/midnight-stage11/uninstall.sh
```

Uninstall only removes the runtime snapshot, the launcher script, the `.desktop` file, and the app icon that were created by this installer. It deliberately keeps:

- The original Git project (`~/Projects/midnight-core-control-center`)
- Midnight Core settings in `~/.config/midnight-core`
- Backups in `~/.local/share/midnight-core/backups` and `~/.config/midnight-core-backup`
- Themes, Plymouth, GDM, GNOME extensions, aliases, and all other system configuration.

If any managed path has been replaced by an unrecognized file or symlink, uninstallation refuses to remove it rather than risk deleting unrelated user data.

## Verify installation

```bash
bash /tmp/midnight-stage11/status.sh
/usr/bin/python3 -m compileall -q ~/.local/share/midnight-core-control-center/app
command -v desktop-file-validate >/dev/null && \
  desktop-file-validate ~/.local/share/applications/io.midnightcore.ControlCenter.desktop
```

`desktop-file-validate` comes from the Fedora `desktop-file-utils` package, if installed. It is optional. GTK4/Libadwaita runtime functionality must still be tested in a real Fedora GNOME Wayland session.

## Tests (synthetic paths, no real config touched)

```bash
python3 -m unittest discover -s /tmp/midnight-stage11/tests -v
```

## Notes

- No `sudo`; per-user installation only. This is not a Fedora RPM or Flatpak yet.
- There is no auto-update; rerun install after changes to the project.
- An installed app snapshot does not automatically include future edits to the Git project.
- This installer does not fix any existing runtime Python/GTK errors in the source; resolve those first.
- GNOME may take a moment to refresh its application grid. Try logging out and in if the application is not visible.
