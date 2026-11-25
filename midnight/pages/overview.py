import time
import weakref

from gi.repository import Gtk, GLib, Pango

from midnight.services.system_info import (
    SystemMonitor,
    system_details,
    gib,
)


class SystemOverview(Gtk.Box):

    def __init__(self):
        super().__init__(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=20,
        )

        self.add_css_class("midnight-overview")

        for method, value in (
            (self.set_margin_top, 32),
            (self.set_margin_bottom, 32),
            (self.set_margin_start, 32),
            (self.set_margin_end, 32),
        ):
            method(value)

        self.monitor = SystemMonitor()
        self.metrics = {}
        self.details = {}

        self.build_interface()
        self.refresh()

        # Weak reference avoids retaining the page unnecessarily.
        page_ref = weakref.ref(self)

        def tick():
            page = page_ref()

            if page is None:
                return GLib.SOURCE_REMOVE

            page.refresh()
            return GLib.SOURCE_CONTINUE

        self._timer_id = GLib.timeout_add_seconds(2, tick)

    def heading(self, title, subtitle):
        group = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=6,
        )

        label = Gtk.Label(label=title, xalign=0)
        label.add_css_class("page-title")

        description = Gtk.Label(
            label=subtitle,
            xalign=0,
            wrap=True,
        )
        description.add_css_class("muted")

        group.append(label)
        group.append(description)

        return group

    def build_interface(self):
        top = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )

        title = self.heading(
            "System Overview",
            "Live monitoring of your Fedora workstation.",
        )
        title.set_hexpand(True)

        refresh_button = Gtk.Button(label="Refresh")
        refresh_button.set_valign(Gtk.Align.CENTER)
        refresh_button.add_css_class("refresh-button")
        refresh_button.connect(
            "clicked",
            lambda *_: self.refresh(),
        )

        top.append(title)
        top.append(refresh_button)
        self.append(top)

        hero = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )
        hero.add_css_class("hero-card")

        badge = Gtk.Label(
            label="MIDNIGHT CORE · SYSTEM MONITOR",
            xalign=0,
        )
        badge.add_css_class("accent-label")

        welcome = Gtk.Label(
            label="Your workstation at a glance",
            xalign=0,
            wrap=True,
        )
        welcome.add_css_class("hero-title")

        self.updated = Gtk.Label(
            label="Collecting system information...",
            xalign=0,
        )
        self.updated.add_css_class("muted")

        hero.append(badge)
        hero.append(welcome)
        hero.append(self.updated)
        self.append(hero)

        grid = Gtk.Grid()
        grid.set_column_spacing(14)
        grid.set_row_spacing(14)
        grid.set_column_homogeneous(True)

        cards = [
            ("cpu", "CPU", "computer-symbolic"),
            ("memory", "Memory", "drive-harddisk-symbolic"),
            ("disk", "Storage", "folder-symbolic"),
            ("battery", "Battery", "battery-symbolic"),
        ]

        for index, (key, title, icon) in enumerate(cards):
            grid.attach(
                self.metric_card(key, title, icon),
                index % 2,
                index // 2,
                1,
                1,
            )

        self.append(grid)

        info_title = Gtk.Label(
            label="System Information",
            xalign=0,
        )
        info_title.add_css_class("section-title")
        self.append(info_title)

        info_box = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=0,
        )
        info_box.add_css_class("system-info-card")

        for key, value in system_details().items():
            info_box.append(self.info_row(key, value))

        self.uptime_label = self.info_row(
            "Uptime", "Calculating..."
        )
        info_box.append(self.uptime_label)

        self.append(info_box)

        footer = Gtk.Label(
            label="LIVE DATA · REFRESH EVERY 2 SECONDS",
            xalign=0,
        )
        footer.add_css_class("page-footer")
        self.append(footer)

    def metric_card(self, key, title, icon_name):
        card = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )
        card.add_css_class("metric-card")
        card.add_css_class(f"metric-{key}")
        card.set_hexpand(True)

        top = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=10,
        )

        icon = Gtk.Image.new_from_icon_name(icon_name)
        icon.add_css_class("accent-icon")

        heading = Gtk.Label(label=title, xalign=0)
        heading.add_css_class("metric-title")
        heading.set_hexpand(True)

        top.append(icon)
        top.append(heading)

        value = Gtk.Label(label="—", xalign=0)
        value.add_css_class("metric-value")

        detail = Gtk.Label(
            label="Waiting for measurements...",
            xalign=0,
            wrap=True,
        )
        detail.add_css_class("muted")

        bar = Gtk.ProgressBar()
        bar.set_fraction(0)
        bar.add_css_class("metric-progress")

        card.append(top)
        card.append(value)
        card.append(detail)
        card.append(bar)

        self.metrics[key] = (value, detail, bar)

        return card

    def info_row(self, name, value):
        row = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
            spacing=12,
        )
        row.add_css_class("system-info-row")

        key = Gtk.Label(label=name, xalign=0)
        key.add_css_class("muted")
        key.set_size_request(150, -1)

        data = Gtk.Label(
            label=value,
            xalign=1,
        )
        data.set_hexpand(True)
        data.set_ellipsize(Pango.EllipsizeMode.END)
        data.set_tooltip_text(value)
        data.add_css_class("info-value")

        row.append(key)
        row.append(data)

        self.details[name] = data

        return row

    def set_metric(self, key, percent, detail):
        value, description, bar = self.metrics[key]

        if percent is None:
            value.set_text("N/A")
            bar.set_fraction(0)
        else:
            percent = max(0.0, min(100.0, percent))

            value.set_text(f"{percent:.0f}%")
            bar.set_fraction(percent / 100)

        description.set_text(detail)

    def refresh(self):
        data = self.monitor.snapshot()

        cpu = data["cpu"]
        self.set_metric(
            "cpu",
            cpu,
            "Measuring CPU activity..." if cpu is None
            else "Current processor utilization",
        )

        memory = data["memory"]

        if memory and memory[1] > 0:
            used, total = memory
            self.set_metric(
                "memory",
                used / total * 100,
                f"{gib(used):.1f} / {gib(total):.1f} GiB used",
            )
        else:
            self.set_metric("memory", None, "Unavailable")

        disk = data["disk"]

        if disk and disk[1] > 0:
            used, total = disk
            self.set_metric(
                "disk",
                used / total * 100,
                f"{gib(used):.1f} / {gib(total):.1f} GiB used",
            )
        else:
            self.set_metric("disk", None, "Unavailable")

        battery = data["battery"]

        if battery is not None:
            percentage, status = battery
            self.set_metric(
                "battery",
                percentage,
                status,
            )
        else:
            self.set_metric(
                "battery",
                None,
                "No battery detected",
            )

        self.details["Uptime"].set_text(data["uptime"])

        self.updated.set_text(
            "Last updated: " + time.strftime("%H:%M:%S")
        )

        return GLib.SOURCE_CONTINUE
