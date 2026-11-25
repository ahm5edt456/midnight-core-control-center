"""GTK4 Developer Tools dashboard, read-only by design."""
from threading import Thread
from time import strftime
from gi.repository import GLib, Gtk
from midnight.services.developer_tools import DeveloperToolsService


class DeveloperToolsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(32)
        self.set_margin_bottom(32)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.set_hexpand(True)
        self.add_css_class("stage-dev-page")
        self.service = DeveloperToolsService()
        self.busy = False
        self._build()
        self.refresh()

    @staticmethod
    def label(text, cls="muted"):
        item = Gtk.Label(label=str(text), xalign=0, wrap=True)
        item.set_selectable(True)
        item.add_css_class(cls)
        return item

    @staticmethod
    def clear(box):
        item = box.get_first_child()
        while item is not None:
            nxt = item.get_next_sibling()
            box.remove(item)
            item = nxt

    def panel(self, name, description):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=11)
        box.add_css_class("stage-dev-panel")
        box.append(self.label(name, "section-title"))
        box.append(self.label(description))
        self.append(box)
        return box

    def _build(self):
        self.append(self.label("Developer Tools", "page-title"))
        self.append(self.label("Git, Docker, compilers and development tools · read-only diagnostics"))

        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.updated = self.label("Collecting tool information…", "stage-dev-status")
        self.updated.set_hexpand(True)
        self.refresh_button = Gtk.Button(label="Refresh")
        self.refresh_button.add_css_class("stage-dev-button")
        self.refresh_button.connect("clicked", lambda *_: self.refresh())
        controls.append(self.updated)
        controls.append(self.refresh_button)
        self.append(controls)

        git_panel = self.panel("Git Project", "Status of the Midnight Core Control Center source repository")
        self.git_state = self.label("Checking repository…", "stage-dev-value")
        self.git_branch = self.label("", "stage-dev-detail")
        self.git_path = self.label("", "stage-dev-detail")
        git_panel.append(self.git_state)
        git_panel.append(self.git_branch)
        git_panel.append(self.git_path)

        docker_panel = self.panel("Docker Containers", "Active containers only; does not start or stop services")
        self.docker_state = self.label("Checking Docker…", "stage-dev-status")
        docker_panel.append(self.docker_state)
        self.containers_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=7)
        docker_panel.append(self.containers_box)

        tools_panel = self.panel("Installed Developer Tools", "Executable versions from your current user environment")
        self.tool_summary = self.label("Checking tools…", "stage-dev-status")
        tools_panel.append(self.tool_summary)
        self.tools_grid = Gtk.Grid(column_spacing=12, row_spacing=12)
        self.tools_grid.set_column_homogeneous(True)
        tools_panel.append(self.tools_grid)

        self.append(self.label("Refresh checks the system again. No sudo, configuration edits, or Docker mutations.", "stage-dev-status"))

    def refresh(self):
        if self.busy:
            return
        self.busy = True
        self.refresh_button.set_sensitive(False)
        self.updated.set_text("Checking developer environment…")

        def worker():
            try:
                data = self.service.snapshot()
                GLib.idle_add(self._render, data, None)
            except Exception as exc:
                GLib.idle_add(self._render, None, str(exc))

        Thread(target=worker, daemon=True).start()

    def _render(self, data, error):
        self.busy = False
        self.refresh_button.set_sensitive(True)
        if error is not None:
            self.updated.set_text("Check failed: " + error[:160])
            return GLib.SOURCE_REMOVE

        git = data["git"]
        self.git_state.set_text(git["state"])
        self.git_branch.set_text("Branch: " + git["branch"])
        self.git_path.set_text("Repository: " + git["detail"])

        docker = data["docker"]
        self.docker_state.set_text(docker["state"])
        self.clear(self.containers_box)
        if not docker["containers"]:
            self.containers_box.append(self.label("No running containers to display."))
        for container in docker["containers"]:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
            row.add_css_class("stage-dev-container")
            name = self.label(container["name"], "stage-dev-value")
            name.set_hexpand(True)
            row.append(name)
            row.append(self.label(container["status"], "stage-dev-detail"))
            self.containers_box.append(row)

        tools = data["tools"]
        self.tool_summary.set_text(f'{sum(t["installed"] for t in tools)} / {len(tools)} tools found')
        child = self.tools_grid.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.tools_grid.remove(child)
            child = nxt
        for i, tool in enumerate(tools):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
            card.add_css_class("stage-dev-tool")
            title = self.label(("● " if tool["installed"] else "○ ") + tool["name"],
                               "stage-dev-installed" if tool["installed"] else "stage-dev-missing")
            card.append(title)
            card.append(self.label(tool["version"], "stage-dev-detail"))
            self.tools_grid.attach(card, i % 2, i // 2, 1, 1)

        self.updated.set_text("Last checked " + strftime("%H:%M:%S"))
        return GLib.SOURCE_REMOVE
