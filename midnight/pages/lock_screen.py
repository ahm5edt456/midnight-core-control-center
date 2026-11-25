"""Midnight Core Control Center: Lock Screen Manager page."""

from datetime import datetime

from gi.repository import Gtk

from midnight.services.lock_screen import (
    LockScreenService,
    TOGGLES,
    CHOICES,
)


LABELS = {
    "breathing-glow": "Breathing Glow",
    "slide-animation": "Slide Animation",
    "avatar-glow": "Avatar Glow",
    "modern-clock": "Modern Clock",
    "accent-color": "Accent Color",
    "animation-speed": "Animation Speed",
    "glow-intensity": "Glow Intensity",
}


class LockScreenPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for setter in (
            self.set_margin_top, self.set_margin_bottom,
            self.set_margin_start, self.set_margin_end,
        ):
            setter(32)

        self.switches = {}
        self.dropdowns = {}
        self.service = None
        self.current = {}

        self.append(self._label("Lock Screen Manager", "page-title"))
        self.append(self._label(
            "Customize Midnight Lock V3 without editing extension files.", "muted"
        ))

        try:
            self.service = LockScreenService()
            self.current = self.service.read()
        except (OSError, RuntimeError, ValueError) as error:
            self._unavailable(str(error))
            return

        self._build_preview()
        effects = self._panel("Visual Effects")
        for key in TOGGLES:
            self._add_switch(effects, key)

        advanced = self._panel("Color & Motion")
        for key in CHOICES:
            self._add_dropdown(advanced, key)

        summary = self._panel("Pending Changes")
        self.summary = self._label("No pending changes", "muted")
        summary.append(self.summary)

        actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        actions.set_halign(Gtk.Align.END)
        self.restore_button = Gtk.Button(label="Restore Previous")
        self.restore_button.add_css_class("lock-secondary-button")
        self.restore_button.connect("clicked", self._restore)
        self.apply_button = Gtk.Button(label="Apply Changes")
        self.apply_button.add_css_class("lock-primary-button")
        self.apply_button.connect("clicked", self._apply)
        actions.append(self.restore_button)
        actions.append(self.apply_button)
        self.append(actions)

        self.status = self._label(
            "Changes remain local to this page until you press Apply.", "muted"
        )
        self.status.set_wrap(True)
        self.status.set_selectable(True)
        self.append(self.status)
        self._update()

    @staticmethod
    def _label(value, css_class):
        label = Gtk.Label(label=value, xalign=0, wrap=True)
        label.add_css_class(css_class)
        return label

    def _panel(self, title):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        panel.add_css_class("lock-panel")
        panel.append(self._label(title, "section-title"))
        self.append(panel)
        return panel

    def _unavailable(self, problem):
        panel = self._panel("Extension Unavailable")
        panel.append(self._label(problem, "lock-error"))
        panel.append(self._label(
            "Check midnight-lock@local and its compiled GSettings schema. "
            "No lock-screen settings were changed.", "muted"
        ))

    def _build_preview(self):
        preview = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=9)
        preview.set_halign(Gtk.Align.FILL)
        preview.add_css_class("lock-preview")
        self.preview = preview
        title = self._label("MIDNIGHT CORE", "lock-preview-accent")
        title.set_halign(Gtk.Align.CENTER)
        preview.append(title)
        self.preview_clock = Gtk.Label(label=datetime.now().strftime("%H:%M"))
        self.preview_clock.add_css_class("lock-preview-clock")
        preview.append(self.preview_clock)
        note = self._label("Design preview · not the live GNOME lock screen", "muted")
        note.set_halign(Gtk.Align.CENTER)
        preview.append(note)
        self.append(preview)

    def _add_switch(self, panel, key):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.add_css_class("lock-row")
        label = self._label(LABELS[key], "appearance-label")
        label.set_hexpand(True)
        row.append(label)
        switch = Gtk.Switch()
        switch.set_valign(Gtk.Align.CENTER)
        switch.set_active(self.current[key])
        switch.connect("notify::active", self._update)
        row.append(switch)
        panel.append(row)
        self.switches[key] = switch

    def _add_dropdown(self, panel, key):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=14)
        row.add_css_class("lock-row")
        label = self._label(LABELS[key], "appearance-label")
        label.set_hexpand(True)
        row.append(label)
        options = list(CHOICES[key])
        dropdown = Gtk.DropDown.new_from_strings(options)
        dropdown.set_size_request(180, -1)
        index = self.current[key]
        if not 0 <= index < len(options):
            raise ValueError(f"Unsupported option index for {key}: {index}")
        dropdown.set_selected(index)
        dropdown.connect("notify::selected", self._update)
        row.append(dropdown)
        panel.append(row)
        self.dropdowns[key] = dropdown

    def _read_form(self):
        return {
            **{key: switch.get_active() for key, switch in self.switches.items()},
            **{key: int(dropdown.get_selected()) for key, dropdown in self.dropdowns.items()},
        }

    def _update(self, *_args):
        if len(self.switches) != len(TOGGLES) or len(self.dropdowns) != len(CHOICES):
            return
        values = self._read_form()
        differences = [LABELS[key] for key in values if values[key] != self.current[key]]
        self.summary.set_text(
            "No pending changes" if not differences
            else f"{len(differences)} pending: " + ", ".join(differences)
        )
        self.apply_button.set_sensitive(bool(differences))
        for i in range(6):
            self.preview.remove_css_class(f"lock-accent-{i}")
        self.preview.add_css_class(f"lock-accent-{values['accent-color']}")

    def _load_form(self, values):
        for key, switch in self.switches.items():
            switch.set_active(values[key])
        for key, dropdown in self.dropdowns.items():
            dropdown.set_selected(values[key])
        self._update()

    def _apply(self, _button):
        try:
            backup = self.service.apply(self._read_form())
            self.current = self.service.read()
            self._load_form(self.current)
            self.status.set_text(
                "Settings applied. Backup: " + backup.name
                if backup else "No changes to apply."
            )
        except Exception as error:
            self.status.set_text(f"Apply failed: {error}")

    def _restore(self, _button):
        try:
            backup = self.service.restore_previous()
            self.current = self.service.read()
            self._load_form(self.current)
            self.status.set_text("Restored settings from " + backup.name)
        except Exception as error:
            self.status.set_text(f"Restore failed: {error}")
