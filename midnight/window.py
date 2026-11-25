from gi.repository import Adw, Gtk


class MidnightWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Midnight Core Control Center")
        self.set_default_size(1000, 700)

        self.build_interface()

    def build_interface(self):

        layout = Adw.ToolbarView()

        header = Adw.HeaderBar()

        title = Adw.WindowTitle(
            title="Midnight Core",
            subtitle="Control Center",
        )

        header.set_title_widget(title)
        layout.add_top_bar(header)

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=24,
        )

        content.set_margin_top(32)
        content.set_margin_bottom(32)
        content.set_margin_start(32)
        content.set_margin_end(32)

        welcome = Adw.StatusPage(
            icon_name="preferences-system-symbolic",
            title="Midnight Core",
            description="Your entire setup. One place.",
        )

        welcome.set_vexpand(True)

        content.append(welcome)

        version = Gtk.Label(
            label="DEVELOPER WORKSTATION · V1.0"
        )

        version.add_css_class("dim-label")

        content.append(version)

        layout.set_content(content)

        self.set_content(layout)
