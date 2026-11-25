from pathlib import Path

import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")
gi.require_version("Gdk", "4.0")

from gi.repository import Adw, Gdk, Gio, Gtk

from midnight.window import MidnightWindow


ROOT = Path(__file__).resolve().parents[1]


class MidnightApplication(Adw.Application):

    def __init__(self):

        super().__init__(
            application_id="io.midnightcore.ControlCenter",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def load_styles(self):

        manager = Adw.StyleManager.get_default()

        manager.set_color_scheme(
            Adw.ColorScheme.FORCE_DARK
        )

        self.css_provider = Gtk.CssProvider()

        self.css_provider.load_from_path(
            str(ROOT / "assets/style.css")
        )

        Gtk.StyleContext.add_provider_for_display(
            Gdk.Display.get_default(),
            self.css_provider,
            Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION,
        )

    def do_activate(self):

        window = self.get_active_window()

        if window is None:

            self.load_styles()

            window = MidnightWindow(
                application=self
            )

        window.present()
