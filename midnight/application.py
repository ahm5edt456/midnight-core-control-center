import gi

gi.require_version("Gtk", "4.0")
gi.require_version("Adw", "1")

from gi.repository import Adw, Gio

from midnight.window import MidnightWindow


class MidnightApplication(Adw.Application):

    def __init__(self):
        super().__init__(
            application_id="io.midnightcore.ControlCenter",
            flags=Gio.ApplicationFlags.DEFAULT_FLAGS,
        )

    def do_activate(self):
        window = self.get_active_window()

        if window is None:
            window = MidnightWindow(application=self)

        window.present()
