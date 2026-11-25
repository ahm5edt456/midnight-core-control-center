# Midnight Core Control Center

A native GTK4 / Libadwaita desktop application that manages a customized Fedora GNOME workstation.

> Adapt this template to your tested release. Do not claim unsupported cross-distro compatibility.

## Features

- Live Overview and performance diagnostics
- Appearance and Midnight Lock preferences
- Plymouth theme selection and read-only GDM information
- Alacritty, Starship and Neovim configuration
- GNOME extension and managed Bash alias controls
- Selective backup, verification, and restore
- Per-user GNOME application launcher

## Supported environment

- Fedora 45 GNOME/Wayland (primary development target)
- `/usr/bin/python3` with `python3-gobject`, `gtk4` and `libadwaita`
- Optional: GNOME extensions, Plymouth CLI, `nvidia-smi`, Git, Alacritty, Neovim, Starship

## Run from source

```bash
sudo dnf install python3-gobject gtk4 libadwaita
/usr/bin/python3 main.py
```

## Install into application menu

Review the included `packaging/install.sh` and run it as your regular user.

```bash
bash packaging/install.sh
```

Then search for **Midnight Core Control Center** in GNOME or run:

```bash
gtk-launch io.midnightcore.ControlCenter
```

## Tests

```bash
python3 scripts/release_suite.py check --project .
```

Review `docs/TEST_PLAN.md` for the required GUI test matrix.

## Security

- No persistent root process; privileged operations require separate authentication.
- Backups are local and may contain private data: do not publish them.
- Source packages do not include personal settings, credentials, or system journal logs.
- Desktop settings may be version-dependent; review backups and recovery steps.

## Screenshots

Add screenshots of your *actual* running application, ideally Overview, Appearance, and Backup Manager. Do not use illustrative mockups as actual screenshots.

## License

Specify the actual license selected by the project owner. A repository without a license is not automatically open source.

## Release notes

See `docs/RELEASE_NOTES_v1.0.0.md`.
