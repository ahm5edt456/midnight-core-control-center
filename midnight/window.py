from midnight.pages.extensions_aliases import ExtensionsPage, AliasesPage
from midnight.pages.developer_settings import DeveloperSettingsPage
from midnight.pages.boot_login import BootLoginPage
from midnight.pages.lock_screen import LockScreenPage
from midnight.pages.appearance import AppearancePage
from midnight.pages.overview import SystemOverview
from pathlib import Path

from gi.repository import Adw, Gtk

from midnight.pages.catalog import PAGES


ROOT = Path(__file__).resolve().parents[1]


class MidnightWindow(Adw.ApplicationWindow):

    def __init__(self, **kwargs):
        super().__init__(**kwargs)

        self.set_title("Midnight Core Control Center")
        self.set_default_size(1120, 780)
        self.set_size_request(760, 520)

        self.add_css_class("midnight-window")

        self.build_interface()

    def build_interface(self):

        toolbar = Adw.ToolbarView()

        header = Adw.HeaderBar()
        header.add_css_class("midnight-header")

        title = Adw.WindowTitle(
            title="Midnight Core",
            subtitle="Control Center",
        )

        header.set_title_widget(title)
        toolbar.add_top_bar(header)

        layout = Gtk.Box(
            orientation=Gtk.Orientation.HORIZONTAL,
        )

        self.stack = Gtk.Stack()

        self.stack.set_hexpand(True)
        self.stack.set_vexpand(True)

        self.stack.set_transition_type(
            Gtk.StackTransitionType.CROSSFADE
        )

        self.stack.set_transition_duration(180)

        self.stack.set_hhomogeneous(False)
        self.stack.set_vhomogeneous(False)

        sidebar = self.build_sidebar()

        layout.append(sidebar)
        layout.append(self.stack)

        for page_id, title, icon, description in PAGES:

            if page_id == "overview":
                page = SystemOverview()
            elif page_id == "appearance":
                page = AppearancePage()
            elif page_id == "lock":
                page = LockScreenPage()
            elif page_id == "boot":
                page = BootLoginPage()
            elif page_id == "terminal":
                page = DeveloperSettingsPage("terminal")
            elif page_id == "neovim":
                page = DeveloperSettingsPage("neovim")
            elif page_id == "extensions":
                page = ExtensionsPage()
            elif page_id == "aliases":
                page = AliasesPage()
            else:
                page = self.build_module(
                    title, icon, description
                )

            self.stack.add_named(
                self.wrap_page(page),
                page_id,
            )

        toolbar.set_content(layout)
        self.set_content(toolbar)

        self.navigation.select_row(
            self.navigation.get_row_at_index(0)
        )

    def build_sidebar(self):

        sidebar = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )

        sidebar.set_size_request(250, -1)
        sidebar.add_css_class("midnight-sidebar")

        brand = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=8,
        )

        brand.set_margin_top(24)
        brand.set_margin_bottom(12)

        logo = Gtk.Image.new_from_file(
            str(ROOT / "assets/logo.svg")
        )

        brand.append(logo)

        name = Gtk.Label(label="MIDNIGHT CORE")
        name.add_css_class("brand-title")

        subtitle = Gtk.Label(label="Developer Workstation")
        subtitle.add_css_class("muted")

        brand.append(name)
        brand.append(subtitle)

        sidebar.append(brand)

        self.navigation = Gtk.ListBox()

        self.navigation.set_selection_mode(
            Gtk.SelectionMode.SINGLE
        )

        self.navigation.add_css_class(
            "midnight-navigation"
        )

        self.navigation.set_activate_on_single_click(True)

        for page_id, title, icon, description in PAGES:

            row = Gtk.ListBoxRow()

            item = Gtk.Box(
                orientation=Gtk.Orientation.HORIZONTAL,
                spacing=12,
            )

            image = Gtk.Image.new_from_icon_name(icon)
            image.add_css_class("navigation-icon")

            label = Gtk.Label(
                label=title,
                xalign=0,
            )

            item.append(image)
            item.append(label)

            row.set_child(item)
            self.navigation.append(row)

        self.navigation.connect(
            "row-selected",
            self.on_navigation_changed,
        )

        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        scroll.set_vexpand(True)
        scroll.set_child(self.navigation)

        sidebar.append(scroll)

        footer = Gtk.Label(
            label="VERSION 0.2.0"
        )

        footer.add_css_class("sidebar-footer")
        sidebar.append(footer)

        return sidebar

    def on_navigation_changed(self, listbox, row):

        if row is None:
            return

        page_id = PAGES[row.get_index()][0]

        self.stack.set_visible_child_name(page_id)

    def wrap_page(self, content):

        scroll = Gtk.ScrolledWindow()

        scroll.set_policy(
            Gtk.PolicyType.NEVER,
            Gtk.PolicyType.AUTOMATIC,
        )

        scroll.add_css_class("midnight-content")
        scroll.set_child(content)

        return scroll

    def page_container(self, title, description):

        page = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=18,
        )

        page.set_margin_top(32)
        page.set_margin_bottom(32)
        page.set_margin_start(32)
        page.set_margin_end(32)

        heading = Gtk.Label(
            label=title,
            xalign=0,
        )

        heading.add_css_class("page-title")

        subtitle = Gtk.Label(
            label=description,
            xalign=0,
            wrap=True,
        )

        subtitle.add_css_class("muted")

        page.append(heading)
        page.append(subtitle)

        return page

    def build_overview(self):

        page = self.page_container(
            "Overview",
            "Your entire setup. One place.",
        )

        hero = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=12,
        )

        hero.add_css_class("hero-card")

        badge = Gtk.Label(
            label="DEVELOPER WORKSTATION",
            xalign=0,
        )

        badge.add_css_class("accent-label")

        title = Gtk.Label(
            label="Welcome to Midnight Core",
            xalign=0,
            wrap=True,
        )

        title.add_css_class("hero-title")

        desc = Gtk.Label(
            label=(
                "Manage your Linux environment, "
                "development tools and system appearance."
            ),
            xalign=0,
            wrap=True,
        )

        desc.add_css_class("muted")

        hero.append(badge)
        hero.append(title)
        hero.append(desc)

        page.append(hero)

        grid = Gtk.Grid(
            column_spacing=14,
            row_spacing=14,
        )

        grid.set_column_homogeneous(True)

        cards = [
            (
                "System",
                "computer-symbolic",
                "System information",
                0,
            ),
            (
                "Appearance",
                "preferences-desktop-theme-symbolic",
                "Desktop customization",
                1,
            ),
            (
                "Development",
                "text-editor-symbolic",
                "Developer tools",
                8,
            ),
            (
                "Backup",
                "document-save-symbolic",
                "Configuration backups",
                10,
            ),
        ]

        for index, card in enumerate(cards):

            widget = self.build_card(*card)

            grid.attach(
                widget,
                index % 2,
                index // 2,
                1,
                1,
            )

        page.append(grid)

        footer = Gtk.Label(
            label="BUILD  ·  LEARN  ·  CREATE"
        )

        footer.add_css_class("page-footer")
        page.append(footer)

        return page

    def build_card(
        self, title, icon, description, page_index
    ):

        button = Gtk.Button()
        button.add_css_class("module-card")

        content = Gtk.Box(
            orientation=Gtk.Orientation.VERTICAL,
            spacing=10,
        )

        image = Gtk.Image.new_from_icon_name(icon)
        image.set_pixel_size(28)
        image.set_halign(Gtk.Align.START)
        image.add_css_class("accent-icon")

        name = Gtk.Label(
            label=title,
            xalign=0,
        )

        name.add_css_class("card-title")

        desc = Gtk.Label(
            label=description,
            xalign=0,
            wrap=True,
        )

        desc.add_css_class("muted")

        content.append(image)
        content.append(name)
        content.append(desc)

        button.set_child(content)

        button.connect(
            "clicked",
            lambda _: self.navigation.select_row(
                self.navigation.get_row_at_index(page_index)
            ),
        )

        return button

    def build_module(self, title, icon, description):

        page = self.page_container(
            title, description
        )

        placeholder = Adw.StatusPage(
            icon_name=icon,
            title=title,
            description="This module is under development.",
        )

        placeholder.add_css_class("module-placeholder")

        page.append(placeholder)

        return page
