"""GTK4 Terminal & Neovim settings pages, compatible with GTK4 on Fedora."""

from pathlib import Path
import shutil
import subprocess

from gi.repository import Gtk

from midnight.services.developer_settings import (
    ALACRITTY, STARSHIP, NVIM_OPTIONS, NVIM_THEME,
    DeveloperSettingsService,
)


class DeveloperSettingsPage(Gtk.Box):
    def __init__(self, mode="terminal"):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        if mode not in ("terminal", "neovim"):
            raise ValueError("Unknown page mode")
        self.mode = mode
        self.service = DeveloperSettingsService()
        self.initial = self.service.read()
        self.widgets = {}
        self.set_margin_top(32)
        self.set_margin_bottom(32)
        self.set_margin_start(32)
        self.set_margin_end(32)

        if mode == "terminal":
            self.append(self._label("Terminal Manager", "page-title"))
            self.append(self._label("Manage Alacritty and Starship without replacing your existing themes or prompt scripts.", "muted"))
            self._build_terminal()
        else:
            self.append(self._label("Neovim IDE Manager", "page-title"))
            self.append(self._label("Control selected editor options and open existing Midnight Core configurations.", "muted"))
            self._build_neovim()

        self._build_actions()
        self._update_summary()

    @staticmethod
    def _label(text, style="muted"):
        widget = Gtk.Label(label=text, xalign=0, wrap=True)
        widget.add_css_class(style)
        widget.set_selectable(style == "dev-status")
        return widget

    def _panel(self, title, description=""):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        box.add_css_class("dev-panel")
        box.append(self._label(title, "section-title"))
        if description:
            box.append(self._label(description))
        self.append(box)
        return box

    def _row(self, panel, title, description, control):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=18)
        row.add_css_class("dev-row")
        labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        labels.set_hexpand(True)
        labels.append(self._label(title, "dev-field-title"))
        if description:
            labels.append(self._label(description))
        row.append(labels)
        control.set_valign(Gtk.Align.CENTER)
        control.set_size_request(130, -1)
        row.append(control)
        panel.append(row)

    def _switch(self, panel, key, title, description=""):
        control = Gtk.Switch()
        control.set_active(bool(self.initial[key]))
        control.connect("notify::active", lambda *_: self._update_summary())
        self.widgets[key] = control
        self._row(panel, title, description, control)
        return control

    def _spin(self, panel, key, title, low, high, step, digits=1):
        adjustment = Gtk.Adjustment(
            value=float(self.initial[key]), lower=low, upper=high,
            step_increment=step, page_increment=step * 5, page_size=0,
        )
        control = Gtk.SpinButton(adjustment=adjustment, climb_rate=0, digits=digits)
        control.connect("value-changed", lambda *_: self._update_summary())
        self.widgets[key] = control
        self._row(panel, title, "", control)

    def _entry(self, panel, key, title):
        entry = Gtk.Entry()
        entry.set_text(str(self.initial[key]))
        entry.connect("changed", lambda *_: self._update_summary())
        entry.set_max_width_chars(23)
        self.widgets[key] = entry
        self._row(panel, title, "Installed font family name", entry)

    def _button(self, label, callback):
        button = Gtk.Button(label=label)
        button.add_css_class("dev-action")
        button.connect("clicked", callback)
        return button

    def _build_terminal(self):
        terminal = self._panel("Alacritty", "Only font and opacity settings are edited; your palette and other sections remain untouched.")
        self._entry(terminal, "alacritty.font_family", "Font Family")
        self._spin(terminal, "alacritty.font_size", "Font Size", 4, 100, .5)
        self._spin(terminal, "alacritty.opacity", "Window Opacity", 0, 1, .05, 2)

        if self.initial["alacritty.has_imports"]:
            terminal.append(self._label(
                "Your Alacritty config imports other TOML files. Alacritty edits are disabled to avoid overriding imported settings.",
                "dev-warning",
            ))
            for key in self.widgets:
                if key.startswith("alacritty."):
                    self.widgets[key].set_sensitive(False)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        actions.set_halign(Gtk.Align.START)
        actions.append(self._button("Open Alacritty Config", lambda *_: self._open_file(ALACRITTY)))
        terminal.append(actions)

        prompt = self._panel("Starship Prompt", "Edit simple prompt options without changing your custom prompt format or palette.")
        self._switch(prompt, "starship.add_newline", "Extra Prompt Line", "Add a blank line between commands")
        self._switch(prompt, "starship.hide_python", "Hide Python Segment", "The Python module will be disabled")
        self._switch(prompt, "starship.hide_git_branch", "Hide Git Branch", "The Git branch module will be disabled")
        prompt.append(self._button("Open Starship Config", lambda *_: self._open_file(STARSHIP)))

    def _build_neovim(self):
        editor = self._panel("Editor Options", "Saved in a clearly marked block inside options.lua; the rest of LazyVim is preserved.")
        self._switch(editor, "nvim.number", "Line Numbers", "Show line numbers in the editor")
        self._switch(editor, "nvim.relativenumber", "Relative Numbers", "Relative line numbering in Normal mode")
        self._switch(editor, "nvim.wrap", "Line Wrapping", "Wrap long lines visually")
        self._switch(editor, "nvim.cursorline", "Highlight Current Line", "Highlight the line under the cursor")

        tools = self._panel("Midnight Core IDE", "Open your real Neovim files and tools. The custom colorscheme is not overwritten.")
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons.set_halign(Gtk.Align.START)
        buttons.set_homogeneous(False)
        buttons.append(self._button("Theme Config", lambda *_: self._open_file(NVIM_THEME)))
        buttons.append(self._button("Editor Options", lambda *_: self._open_file(NVIM_OPTIONS)))
        tools.append(buttons)
        buttons2 = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        buttons2.set_halign(Gtk.Align.START)
        buttons2.append(self._button("Plugin Manager", lambda *_: self._launch_nvim("+Lazy")))
        buttons2.append(self._button("Health Check", lambda *_: self._launch_nvim("+checkhealth")))
        buttons2.append(self._button("Keymap Center", lambda *_: self._launch_nvim("+MidnightKeys")))
        tools.append(buttons2)
        if not self.initial["nvim.exists"]:
            editor.append(self._label("Neovim options.lua was not found. Changes to editor options are unavailable.", "dev-warning"))
            for key in self.widgets:
                self.widgets[key].set_sensitive(False)

    def _build_actions(self):
        self.summary = self._label("", "dev-summary")
        self.append(self.summary)

        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        buttons.set_halign(Gtk.Align.END)
        buttons.append(self._button("Reload", self._reload))
        buttons.append(self._button("Restore Previous", self._restore))
        apply = self._button("Apply Changes", self._apply)
        apply.add_css_class("dev-apply")
        buttons.append(apply)
        self.append(buttons)

        self.status = self._label("No changes made to your system yet.", "dev-status")
        self.append(self.status)

    def _form(self):
        result = {}
        for key, widget in self.widgets.items():
            if isinstance(widget, Gtk.Switch):
                value = widget.get_active()
            elif isinstance(widget, Gtk.SpinButton):
                value = widget.get_value()
            else:
                value = widget.get_text().strip()
            result[key] = value
        return result

    def _update_summary(self):
        if not hasattr(self, "summary"):
            return
        changes = [key for key, value in self._form().items() if value != self.initial[key]]
        self.summary.set_text(
            f"Pending changes ({len(changes)}): " + ", ".join(changes) if changes else "No pending changes"
        )

    def _reload(self, *_):
        try:
            self.initial = self.service.read()
            for key, widget in self.widgets.items():
                val = self.initial[key]
                if isinstance(widget, Gtk.Switch):
                    widget.set_active(bool(val))
                elif isinstance(widget, Gtk.SpinButton):
                    widget.set_value(float(val))
                else:
                    widget.set_text(str(val))
            self._update_summary()
            self.status.set_text("Reloaded current settings from disk.")
        except Exception as err:
            self.status.set_text(f"Reload failed: {err}")

    def _apply(self, *_):
        try:
            # Only send changes selected by the user; never write all defaults.
            changes = {key: val for key, val in self._form().items() if self.initial[key] != val}
            archive = self.service.apply(changes)
            self._reload()
            if archive is None:
                self.status.set_text("No changes to apply.")
            else:
                self.status.set_text(f"Saved. Backup: {archive.name}. Restart Neovim to reload its options.")
        except Exception as err:
            self.status.set_text(f"Apply failed: {err}")

    def _restore(self, *_):
        try:
            path = self.service.restore_previous()
            self._reload()
            self.status.set_text(f"Restored configuration from {path.name}.")
        except Exception as err:
            self.status.set_text(f"Restore failed: {err}")

    def _open_file(self, path: Path):
        if not path.is_file():
            self.status.set_text(f"File does not exist: {path}")
            return
        self._launch_nvim(str(path))

    def _launch_nvim(self, target):
        if not shutil.which("alacritty") or not shutil.which("nvim"):
            self.status.set_text("Alacritty or Neovim was not found in PATH.")
            return
        try:
            subprocess.Popen(
                ["alacritty", "-e", "nvim", target],
                start_new_session=True,
            )
            self.status.set_text("Opened Neovim in Alacritty.")
        except OSError as err:
            self.status.set_text(f"Unable to open Neovim: {err}")
