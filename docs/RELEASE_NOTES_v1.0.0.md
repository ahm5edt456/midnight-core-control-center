# Midnight Core Control Center v1.0.0

**Draft — publish only after Fedora GUI acceptance tests pass.**

A native GTK4 and Libadwaita desktop control center for a Fedora GNOME developer workstation. The application brings workstation configuration and diagnostics into a single interface.

## Features

- Overview: CPU, memory, disk and device information
- Appearance: GNOME preferences, icons, cursors, typography and wallpaper with backup/restore
- Lock Screen: local Midnight Lock extension preferences
- Boot & Login: Plymouth theme management with explicit administrator authentication; read-only GDM diagnostics
- Terminal & Neovim: user-level Alacritty, Starship and Neovim settings
- GNOME Extensions & Aliases: extension management and managed Bash aliases
- Performance & Diagnostics: system and tool status, process usage and limited journal views
- Backup & Restore: selective archive creation, integrity verification and safeguarded restore
- Packaging: per-user application launcher and GNOME desktop integration (not RPM/Flatpak)

## Requirements

Fedora with GTK4, Libadwaita and PyGObject installed for `/usr/bin/python3`; GNOME/Wayland is the primary target. Optional integrations require the corresponding local tools/extensions. No blanket root privileges required; changing Plymouth requires explicit authentication.

## Limitations

- Some GNOME settings are version-dependent; GTK/libadwaita apps may not honor custom legacy GTK themes.
- GPU usage needs a supported provider, such as `nvidia-smi` for NVIDIA.
- Boot changes need elevated permissions and may require rebuilding initramfs; GDM edits are not provided.
- Backups may contain private user data and are not encrypted; never publish them.
- A local Python/GTK application bundle is provided; no RPM/Flatpak artifact or auto-updater.
- **Manual validation status: pending, until you complete the test plan.**
