"""GTK4 Boot & Login Manager: Plymouth with polkit, GDM read-only."""

import subprocess
import threading

from gi.repository import GLib, Gtk

from midnight.services.boot_login import BootLoginService


class BootLoginPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(32)
        self.set_margin_bottom(32)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.service = BootLoginService()
        self.state = None
        self.choices = []
        self.busy = False
        self.pending_dialog = None

        self.append(self._label("Boot & Login Manager", "page-title"))
        self.append(self._label(
            "Control Plymouth boot themes and inspect GDM configuration safely.",
            "muted",
        ))

        self._build_plymouth()
        self._build_gdm()
        self._build_actions()
        self.refresh()

    @staticmethod
    def _label(text, css):
        label = Gtk.Label(label=text, xalign=0, wrap=True)
        label.add_css_class(css)
        label.set_selectable(css in ("boot-status", "boot-info-value"))
        return label

    def _panel(self, title):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=14)
        panel.add_css_class("boot-panel")
        panel.append(self._label(title, "section-title"))
        self.append(panel)
        return panel

    def _line(self, panel, name):
        row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        row.add_css_class("boot-line")
        heading = self._label(name, "muted")
        heading.set_size_request(135, -1)
        value = self._label("—", "boot-info-value")
        value.set_hexpand(True)
        row.append(heading)
        row.append(value)
        panel.append(row)
        return value

    def _build_plymouth(self):
        panel = self._panel("Plymouth · Boot Screen")
        self.current_label = self._line(panel, "Active Theme")

        self.preview = Gtk.Picture()
        self.preview.set_content_fit(Gtk.ContentFit.CONTAIN)
        self.preview.set_size_request(420, 160)
        self.preview.add_css_class("boot-preview")
        panel.append(self.preview)
        self.preview_note = self._label(
            "Image assets are not an exact preview of boot animation.", "muted"
        )
        panel.append(self.preview_note)

        label = self._label("Installed Theme", "appearance-label")
        panel.append(label)
        self.dropdown = Gtk.DropDown.new_from_strings(["Loading..."])
        self.dropdown.connect("notify::selected", self._on_theme_selected)
        panel.append(self.dropdown)

        self.apply_button = Gtk.Button(label="Apply Plymouth Theme")
        self.apply_button.add_css_class("boot-primary-button")
        self.apply_button.connect("clicked", self._apply_clicked)
        panel.append(self.apply_button)
        panel.append(self._label(
            "Applying requires administrator authentication and rebuilds initramfs. "
            "The result appears on a subsequent boot; do not interrupt the rebuild.",
            "boot-warning",
        ))

    def _build_gdm(self):
        panel = self._panel("GDM · Login Screen (Read-only)")
        self.gdm_status = self._line(panel, "Display Manager")
        self.gdm_config = self._line(panel, "GDM Config")
        self.gdm_logo = self._line(panel, "Configured Logo")
        self.gdm_logo_source = self._line(panel, "Logo Source")
        panel.append(self._label(
            "GDM settings are displayed only. This application does not edit dconf "
            "profiles, enable automatic login, or restart the display manager.",
            "muted",
        ))

    def _build_actions(self):
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        buttons.set_halign(Gtk.Align.END)

        refresh = Gtk.Button(label="Refresh")
        refresh.add_css_class("boot-secondary-button")
        refresh.connect("clicked", lambda *_: self.refresh())
        self.refresh_button = refresh

        restore = Gtk.Button(label="Restore Previous Theme")
        restore.add_css_class("boot-secondary-button")
        restore.connect("clicked", self._restore_clicked)
        self.restore_button = restore

        buttons.append(refresh)
        buttons.append(restore)
        self.append(buttons)

        self.spinner = Gtk.Spinner()
        self.spinner.set_halign(Gtk.Align.START)
        self.spinner.set_visible(False)
        self.append(self.spinner)

        self.status = self._label(
            "Select an installed boot theme, then confirm the change.",
            "boot-status",
        )
        self.append(self.status)

    def _set_busy(self, busy):
        self.busy = busy
        self.dropdown.set_sensitive(not busy and bool(self.choices))
        self.refresh_button.set_sensitive(not busy)
        self.restore_button.set_sensitive(not busy and bool(self.service.previous_theme()))
        if busy:
            self.spinner.set_visible(True)
            self.spinner.start()
        else:
            self.spinner.stop()
            self.spinner.set_visible(False)
        self._update_apply()

    def refresh(self):
        if self.busy:
            return
        self.state = self.service.snapshot()
        self.choices = self.state["themes"]
        self.dropdown.set_model(Gtk.StringList.new(self.choices or ["No themes found"]))
        current = self.state["current"]
        self.current_label.set_text(current or "Unavailable")
        if current in self.choices:
            self.dropdown.set_selected(self.choices.index(current))
        else:
            self.dropdown.set_selected(Gtk.INVALID_LIST_POSITION)

        gdm = self.state["gdm"]
        self.gdm_status.set_text(gdm["status"])
        self.gdm_config.set_text(gdm["custom_conf"])
        self.gdm_logo.set_text(gdm["logo"])
        self.gdm_logo_source.set_text(gdm["logo_source"])
        self._on_theme_selected()
        self._set_busy(False)

    def _selected_theme(self):
        index = self.dropdown.get_selected()
        return self.choices[index] if 0 <= index < len(self.choices) else None

    def _on_theme_selected(self, *_args):
        selected = self._selected_theme()
        path = self.service.preview_image(selected) if selected else None
        self.preview.set_visible(bool(path))
        if path:
            self.preview.set_filename(str(path))
            self.preview_note.set_text(
                f"Theme asset preview: {path.name} (not the full animation)"
            )
        else:
            self.preview_note.set_text("No preview image supplied by this theme.")
        self._update_apply()

    def _update_apply(self):
        self.apply_button.set_sensitive(
            not self.busy and bool(self.service.pkexec_exe)
            and bool(self.service.plymouth_exe)
            and self._selected_theme() is not None
            and self._selected_theme() != self.state["current"]
        )

    def _apply_clicked(self, _button):
        selected = self._selected_theme()
        if selected:
            self._confirm(selected, restore=False)

    def _restore_clicked(self, _button):
        selected = self.service.previous_theme()
        if not selected:
            self.status.set_text("No previous boot theme backup found.")
        elif selected not in self.choices:
            self.status.set_text("Previous theme is no longer installed; restore unavailable.")
        else:
            self._confirm(selected, restore=True)

    def _confirm(self, selected, restore):
        if self.busy:
            return
        if selected == self.state["current"]:
            self.status.set_text("This theme is already active.")
            return
        try:
            self.service.privileged_command(selected)
        except Exception as error:
            self.status.set_text(str(error))
            return

        parent = self.get_root()
        dialog = Gtk.MessageDialog(
            transient_for=parent,
            modal=True,
            message_type=Gtk.MessageType.WARNING,
            buttons=Gtk.ButtonsType.YES_NO,
            text=("Restore previous Plymouth theme?" if restore
                  else "Change Plymouth boot theme?"),
        )
        dialog.props.secondary_text = (
            f"Selected: {selected}\n\n"
            "This requires administrator authentication and rebuilds initramfs. "
            "Do not reboot, suspend, or power off during the operation."
        )
        dialog.connect("response", self._on_confirm_response, selected)
        self.pending_dialog = dialog
        dialog.present()

    def _on_confirm_response(self, dialog, response, selected):
        dialog.destroy()
        self.pending_dialog = None
        if response == Gtk.ResponseType.YES:
            self._start_change(selected)

    def _start_change(self, selected):
        if self.busy:
            return
        try:
            args = self.service.privileged_command(selected)
        except Exception as error:
            self.status.set_text(f"Unable to apply: {error}")
            return
        previous = self.service.current_theme()
        self._set_busy(True)
        self.status.set_text(
            f"Applying '{selected}' and rebuilding initramfs. "
            "Do not power off or reboot until completion."
        )

        def run():
            try:
                result = subprocess.run(
                    args, capture_output=True, text=True,
                    timeout=600, check=False,
                )
                details = (result.stderr or result.stdout or "").strip()[-1200:]
                GLib.idle_add(
                    self._finished, result.returncode, details,
                    previous, selected,
                )
            except (OSError, subprocess.TimeoutExpired) as error:
                GLib.idle_add(self._finished, 1, str(error), previous, selected)

        threading.Thread(target=run, daemon=True).start()

    def _finished(self, code, details, previous, selected):
        self._set_busy(False)
        self.refresh()
        current = self.state["current"]
        if code == 0 and current == selected:
            try:
                self.service.record_success(previous, selected)
                self.status.set_text(
                    f"Applied '{selected}'. Boot will show the new theme on a subsequent boot. "
                    "Previous theme recorded for restore."
                )
            except OSError as error:
                self.status.set_text(
                    f"Applied '{selected}', but backup could not be saved: {error}"
                )
        elif code == 0:
            self.status.set_text(
                "The utility reported success, but the selected theme could not be "
                f"verified (current: {current or 'unknown'}). Review Plymouth before reboot."
            )
        else:
            self.status.set_text(
                "Change failed or authentication was canceled. "
                f"Current theme: {current or 'unknown'}. "
                f"Details: {details or 'No additional output'}"
            )
        return GLib.SOURCE_REMOVE
