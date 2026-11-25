from pathlib import Path
from urllib.parse import urlparse, unquote

from gi.repository import Gio, Gtk

from midnight.services.appearance import (
    AppearanceService,
    available_themes,
    available_icons,
    available_cursors,
)


IMAGE_EXTENSIONS = {
    ".jpg", ".jpeg", ".png", ".webp", ".bmp"
}


class AppearancePage(Gtk.Box):

    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
        )

        self.service = AppearanceService()
        self.current = self.service.snapshot()

        self.dropdowns = {}
        self.options = {}
        self.font_entries = {}
        self.wallpaper_path = None
        self.chooser = None

        self.set_margin_top(32)
        self.set_margin_bottom(32)
        self.set_margin_start(32)
        self.set_margin_end(32)

        self.build_interface()

    def heading(self, text, css_class):
        label = Gtk.Label(
            label=text,
            xalign=0,
            wrap=True,
        )
        label.add_css_class(css_class)
        return label

    def panel(self, title):
        panel = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=16,
        )
        panel.add_css_class("appearance-panel")

        panel.append(
            self.heading(title, "section-title")
        )

        self.append(panel)
        return panel

    def add_row(self, panel, label, control):
        row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=16,
        )
        row.add_css_class("appearance-row")

        title = self.heading(label, "appearance-label")
        title.set_hexpand(True)
        title.set_valign(Gtk.Align.CENTER)

        control.set_size_request(190, -1)

        row.append(title)
        row.append(control)
        panel.append(row)

    def add_dropdown(
        self, panel, key, label, choices
    ):
        current = self.current[key]
        options = sorted(
            set(choices) | {current},
            key=str.casefold,
        )

        dropdown = Gtk.DropDown.new_from_strings(options)
        dropdown.set_selected(options.index(current))

        self.options[key] = options
        self.dropdowns[key] = dropdown

        dropdown.connect(
            "notify::selected",
            lambda *_: self.update_summary(),
        )

        self.add_row(panel, label, dropdown)

    def add_font(self, panel, key, label):
        entry = Gtk.Entry()
        entry.set_text(self.current[key])
        entry.set_placeholder_text("Font family and size")

        entry.connect(
            "changed",
            lambda *_: self.update_summary(),
        )

        self.font_entries[key] = entry

        self.add_row(panel, label, entry)

    def selected(self, key):
        dropdown = self.dropdowns[key]
        index = dropdown.get_selected()

        return self.options[key][index]

    def build_interface(self):
        self.append(
            self.heading(
                "Appearance Manager",
                "page-title",
            )
        )

        self.append(
            self.heading(
                "Customize GNOME appearance safely.",
                "muted",
            )
        )

        appearance = self.panel("Desktop Appearance")

        schemes = [
            ("System Default", "default"),
            ("Prefer Dark", "prefer-dark"),
            ("Prefer Light", "prefer-light"),
        ]

        self.scheme_values = [
            value for _, value in schemes
        ]

        self.scheme = Gtk.DropDown.new_from_strings(
            [label for label, _ in schemes]
        )

        selected_scheme = self.current["scheme"]

        if selected_scheme in self.scheme_values:
            self.scheme.set_selected(
                self.scheme_values.index(selected_scheme)
            )

        self.scheme.connect(
            "notify::selected",
            lambda *_: self.update_summary(),
        )

        self.add_row(
            appearance, "Color Scheme", self.scheme
        )

        self.add_dropdown(
            appearance,
            "gtk",
            "GTK Theme",
            available_themes(),
        )

        self.add_dropdown(
            appearance,
            "icons",
            "Icon Theme",
            available_icons(),
        )

        self.add_dropdown(
            appearance,
            "cursor",
            "Cursor Theme",
            available_cursors(),
        )

        fonts = self.panel("Typography")

        self.add_font(
            fonts, "font", "Interface Font"
        )

        self.add_font(
            fonts, "document_font", "Document Font"
        )

        self.add_font(
            fonts, "mono_font", "Monospace Font"
        )

        wallpaper = self.panel("Wallpaper")

        self.picture = Gtk.Picture()
        self.picture.set_size_request(420, 210)
        self.picture.set_content_fit(
            Gtk.ContentFit.CONTAIN
        )
        self.picture.add_css_class(
            "appearance-wallpaper"
        )

        wallpaper.append(self.picture)

        self.wallpaper_label = self.heading(
            "No image selected", "muted"
        )
        wallpaper.append(self.wallpaper_label)

        choose = Gtk.Button(label="Choose Wallpaper")
        choose.add_css_class("appearance-choose")
        choose.connect(
            "clicked", self.choose_wallpaper
        )
        choose.set_halign(Gtk.Align.START)
        wallpaper.append(choose)

        current_uri = (
            self.current["wallpaper_dark"]
            if selected_scheme == "prefer-dark"
            else self.current["wallpaper_light"]
        )

        self.show_wallpaper_uri(current_uri)

        preview = self.panel("Pending Changes")

        self.summary = self.heading(
            "", "appearance-summary"
        )
        preview.append(self.summary)

        actions = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )
        actions.set_halign(Gtk.Align.END)

        restore = Gtk.Button(label="Restore Previous")
        restore.add_css_class("appearance-restore")
        restore.connect(
            "clicked", self.restore_previous
        )

        apply_button = Gtk.Button(
            label="Apply Changes"
        )
        apply_button.add_css_class(
            "appearance-apply"
        )
        apply_button.connect(
            "clicked", self.apply_changes
        )

        actions.append(restore)
        actions.append(apply_button)

        self.append(actions)

        self.status = self.heading(
            "Changes will not be applied until you press Apply.",
            "muted",
        )
        self.status.set_selectable(True)
        self.append(self.status)

        self.update_summary()

    def show_wallpaper_uri(self, uri):
        parsed = urlparse(uri)

        if parsed.scheme != "file":
            self.picture.set_visible(False)
            self.wallpaper_label.set_text(
                "Current wallpaper preview unavailable"
            )
            return

        path = Path(unquote(parsed.path))

        if not path.is_file():
            self.picture.set_visible(False)
            self.wallpaper_label.set_text(
                "Wallpaper file not found"
            )
            return

        if path.suffix.lower() not in IMAGE_EXTENSIONS:
            self.picture.set_visible(False)
            self.wallpaper_label.set_text(
                path.name + " (preview unavailable)"
            )
            return

        self.picture.set_filename(str(path))
        self.picture.set_visible(True)
        self.wallpaper_label.set_text(path.name)

    def choose_wallpaper(self, _button):
        self.chooser = Gtk.FileChooserNative.new(
            "Choose Wallpaper",
            self.get_root(),
            Gtk.FileChooserAction.OPEN,
            "Select",
            "Cancel",
        )

        image_filter = Gtk.FileFilter()
        image_filter.set_name("Images")

        for mime in (
            "image/jpeg",
            "image/png",
            "image/webp",
            "image/bmp",
        ):
            image_filter.add_mime_type(mime)

        self.chooser.add_filter(image_filter)

        self.chooser.connect(
            "response", self.on_file_chosen
        )
        self.chooser.show()

    def on_file_chosen(self, chooser, response):
        if response == Gtk.ResponseType.ACCEPT:
            file = chooser.get_file()
            path = file.get_path() if file else None

            if path:
                self.wallpaper_path = Path(path)
                self.show_wallpaper_uri(
                    self.wallpaper_path.resolve().as_uri()
                )
                self.update_summary()

        chooser.destroy()
        self.chooser = None

    def values_from_form(self):
        values = {
            "scheme": self.scheme_values[
                self.scheme.get_selected()
            ],
            "gtk": self.selected("gtk"),
            "icons": self.selected("icons"),
            "cursor": self.selected("cursor"),
        }

        for key, entry in self.font_entries.items():
            value = entry.get_text().strip()

            if not value:
                raise ValueError(
                    f"Font cannot be empty: {key}"
                )

            values[key] = value

        if self.wallpaper_path is not None:
            path = self.wallpaper_path.expanduser().resolve()

            if not path.is_file():
                raise FileNotFoundError(
                    "Selected wallpaper no longer exists"
                )

            if path.suffix.lower() not in IMAGE_EXTENSIONS:
                raise ValueError(
                    "Unsupported wallpaper file type"
                )

            uri = path.as_uri()

            # Same wallpaper in both appearance modes.
            values["wallpaper_light"] = uri
            values["wallpaper_dark"] = uri

        return values

    def update_summary(self):
        if not hasattr(self, "summary"):
            return

        try:
            values = self.values_from_form()
        except (ValueError, FileNotFoundError) as error:
            self.summary.set_text(str(error))
            return

        differences = [
            key for key, value in values.items()
            if value != self.current.get(key)
        ]

        if differences:
            self.summary.set_text(
                f"{len(differences)} pending setting(s): "
                + ", ".join(differences)
            )
        else:
            self.summary.set_text(
                "No pending changes"
            )

    def apply_changes(self, _button):
        try:
            values = self.values_from_form()
            backup = self.service.apply(values)

            self.current = self.service.snapshot()
            self.wallpaper_path = None

            if backup is None:
                message = "No changes to apply."
            else:
                message = (
                    "Changes applied successfully. "
                    f"Backup: {backup.name}"
                )

            self.status.set_text(message)
            self.update_summary()

        except Exception as error:
            self.status.set_text(
                f"Apply failed: {error}"
            )

    def restore_previous(self, _button):
        try:
            self.service.restore_previous()
            self.current = self.service.snapshot()
            self.wallpaper_path = None

            for key, dropdown in self.dropdowns.items():
                value = self.current[key]

                if value in self.options[key]:
                    dropdown.set_selected(
                        self.options[key].index(value)
                    )

            value = self.current["scheme"]

            if value in self.scheme_values:
                self.scheme.set_selected(
                    self.scheme_values.index(value)
                )

            for key, entry in self.font_entries.items():
                entry.set_text(self.current[key])

            uri = (
                self.current["wallpaper_dark"]
                if value == "prefer-dark"
                else self.current["wallpaper_light"]
            )

            self.show_wallpaper_uri(uri)

            self.status.set_text(
                "Previous appearance settings restored."
            )
            self.update_summary()

        except Exception as error:
            self.status.set_text(
                f"Restore failed: {error}"
            )
