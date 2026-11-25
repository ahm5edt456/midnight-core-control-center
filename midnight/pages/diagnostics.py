"""GTK4 read-only performance and diagnostics dashboard."""

from threading import Thread
from time import strftime

from gi.repository import GLib, Gtk, Pango

from midnight.services.diagnostics import DiagnosticsService


class DiagnosticsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        self.set_margin_top(32)
        self.set_margin_bottom(32)
        self.set_margin_start(32)
        self.set_margin_end(32)
        self.set_hexpand(True)
        self.add_css_class('stage9-page')
        self.service = DiagnosticsService()
        self.live_busy = False
        self.action_busy = False
        self.process_cache = []
        self.metrics = {}
        self.build()
        self.refresh_live()
        self._was_rooted = False
        self._source_id = GLib.timeout_add_seconds(8, self._timer)

    @staticmethod
    def label(value, css='muted'):
        widget = Gtk.Label(label=str(value), xalign=0, wrap=True)
        widget.add_css_class(css)
        return widget

    @staticmethod
    def button(value, handler):
        button = Gtk.Button(label=value)
        button.add_css_class('stage9-button')
        button.connect('clicked', lambda *_: handler())
        return button

    def panel(self, heading, detail=None):
        wrapper = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        wrapper.add_css_class('stage9-panel')
        wrapper.append(self.label(heading, 'section-title'))
        if detail:
            wrapper.append(self.label(detail))
        self.append(wrapper)
        return wrapper

    def build(self):
        self.append(self.label('Performance & Diagnostics', 'page-title'))
        self.append(self.label('Read-only Fedora diagnostics · No sudo · No service restarts'))

        top = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
        self.updated = self.label('Collecting initial measurements…', 'stage9-status')
        self.updated.set_hexpand(True)
        top.append(self.updated)
        top.append(self.button('Refresh Live', self.refresh_live))
        self.append(top)

        grid = Gtk.Grid(column_spacing=14, row_spacing=14)
        grid.set_column_homogeneous(True)
        cards = [('cpu', 'CPU', 'computer-symbolic'),
                 ('memory', 'Memory', 'drive-harddisk-symbolic'),
                 ('disk', 'Storage', 'folder-symbolic'),
                 ('gpu', 'GPU', 'video-display-symbolic')]
        for i, (key, title, icon_name) in enumerate(cards):
            card = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
            card.add_css_class('stage9-metric')
            card.add_css_class('stage9-' + key)
            top_row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            top_row.append(Gtk.Image.new_from_icon_name(icon_name))
            top_row.append(self.label(title, 'stage9-metric-heading'))
            card.append(top_row)
            value = self.label('—', 'stage9-value')
            detail = self.label('Waiting for measurements…')
            bar = Gtk.ProgressBar()
            bar.add_css_class('stage9-progress')
            card.append(value)
            card.append(detail)
            card.append(bar)
            self.metrics[key] = (value, detail, bar)
            grid.attach(card, i % 2, i // 2, 1, 1)
        self.append(grid)
        self.load_average = self.label('Load average: reading…', 'stage9-status')
        self.append(self.load_average)

        process_panel = self.panel(
            'Top Processes', 'CPU% from ps is an average, not an instantaneous sample. '
            'Memory column shows resident memory (RSS).')
        process_toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.process_search = Gtk.SearchEntry()
        self.process_search.set_hexpand(True)
        self.process_search.set_placeholder_text('Filter processes by PID or name…')
        self.process_search.connect('search-changed', lambda *_: self.render_processes())
        process_toolbar.append(self.process_search)
        process_panel.append(process_toolbar)
        self.process_list = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=0)
        process_panel.append(self.process_list)

        system_panel = self.panel('Services & Developer Tools',
            'Current status of systemd services and installed development tools. '
            'These checks do not modify services or files.')
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        controls.append(self.button('Check Services', self.check_services))
        controls.append(self.button('Check Tools', self.check_tools))
        system_panel.append(controls)
        self.check_result = self.label('Choose a check above.', 'stage9-output')
        self.check_result.set_selectable(True)
        system_panel.append(self.check_result)

        logs_panel = self.panel('Recent Error Logs',
            'Only the last 35 error-level entries are requested. '
            'Access to system journals may be limited for normal users.')
        log_actions = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        log_actions.append(self.button('User Errors', lambda: self.show_logs('user')))
        log_actions.append(self.button('Boot Errors', lambda: self.show_logs('boot')))
        logs_panel.append(log_actions)

        # A monospace, selectable log view with a bounded height.
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(170)
        scroll.set_max_content_height(270)
        scroll.set_propagate_natural_height(True)
        self.log_view = Gtk.TextView()
        self.log_view.set_editable(False)
        self.log_view.set_cursor_visible(False)
        self.log_view.set_monospace(True)
        self.log_view.set_wrap_mode(Gtk.WrapMode.CHAR)
        self.log_view.add_css_class('stage9-log')
        self.log_view.get_buffer().set_text('Click a log button to inspect recent errors.')
        scroll.set_child(self.log_view)
        logs_panel.append(scroll)

        self.action_status = self.label('No diagnostic actions run yet.', 'stage9-status')
        self.action_status.set_selectable(True)
        self.append(self.action_status)

    def _timer(self):
        if self.get_root() is None:
            return GLib.SOURCE_REMOVE if self._was_rooted else GLib.SOURCE_CONTINUE
        self._was_rooted = True
        self.refresh_live()
        return GLib.SOURCE_CONTINUE

    def refresh_live(self):
        if self.live_busy:
            return
        self.live_busy = True

        def worker():
            try:
                data = self.service.live()
                processes = self.service.processes(limit=12)
                GLib.idle_add(self._render_live, data, processes, None)
            except Exception as error:
                GLib.idle_add(self._render_live, None, None, str(error))

        Thread(target=worker, daemon=True).start()

    def _render_live(self, data, processes, error):
        self.live_busy = False
        if error:
            self.updated.set_text('Unable to update metrics: ' + error)
            return GLib.SOURCE_REMOVE
        for key in ('cpu', 'memory', 'disk', 'gpu'):
            self._set_metric(key, data[key]['value'], data[key]['detail'])
        self.load_average.set_text('Load average (1 / 5 / 15 min): ' + data['load'])
        self.process_cache = processes
        self.render_processes()
        self.updated.set_text('Last refresh: ' + strftime('%H:%M:%S') + ' · Updates every 8 seconds')
        return GLib.SOURCE_REMOVE

    def _set_metric(self, key, value, detail):
        number, subtitle, bar = self.metrics[key]
        number.set_text('N/A' if value is None else f'{value:.1f}%')
        subtitle.set_text(detail)
        bar.set_fraction(0 if value is None else min(1, max(0, value / 100)))
        bar.set_sensitive(value is not None)

    def render_processes(self):
        child = self.process_list.get_first_child()
        while child:
            nxt = child.get_next_sibling()
            self.process_list.remove(child)
            child = nxt

        needle = self.process_search.get_text().strip().casefold()
        processes = [p for p in self.process_cache
                     if needle in p['name'].casefold() or needle in str(p['pid'])]
        header = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        header.add_css_class('stage9-process-header')
        for col, width in [('PID', 75), ('Process', 0), ('CPU', 85), ('RAM', 95)]:
            text = self.label(col, 'stage9-key')
            if width:
                text.set_size_request(width, -1)
            else:
                text.set_hexpand(True)
            header.append(text)
        self.process_list.append(header)
        if not processes:
            self.process_list.append(self.label('No matching processes.', 'stage9-status'))
            return
        for proc in processes:
            row = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            row.add_css_class('stage9-process-row')
            for value, width in ((str(proc['pid']), 75), (proc['name'], 0),
                                 (f"{proc['cpu']:.1f}%", 85),
                                 (f"{proc['memory_mib']:.1f} MiB", 95)):
                cell = self.label(value, 'stage9-process-value')
                cell.set_ellipsize(Pango.EllipsizeMode.END)
                if width:
                    cell.set_size_request(width, -1)
                else:
                    cell.set_hexpand(True)
                row.append(cell)
            self.process_list.append(row)

    def background(self, status, job, callback):
        if self.action_busy:
            self.action_status.set_text('A diagnostic check is already running.')
            return
        self.action_busy = True
        self.action_status.set_text(status + '…')

        def worker():
            try:
                result = job()
            except Exception as error:
                GLib.idle_add(self._finish, callback, None, str(error))
            else:
                GLib.idle_add(self._finish, callback, result, None)

        Thread(target=worker, daemon=True).start()

    def _finish(self, callback, result, error):
        self.action_busy = False
        if error:
            self.action_status.set_text('Check failed: ' + error)
        else:
            try:
                callback(result)
                self.action_status.set_text('Completed: ' + strftime('%H:%M:%S'))
            except Exception as err:
                self.action_status.set_text('Display error: ' + str(err))
        return GLib.SOURCE_REMOVE

    def check_services(self):
        self.background('Checking systemd services', self.service.services, self._services_done)

    def _services_done(self, result):
        lines = ['SYSTEM SERVICES']
        lines += [f'{name:18} {status}' for name, status in result['system'].items()]
        lines += ['', 'FAILED USER UNITS', result['failed_user_units']]
        self.check_result.set_text('\n'.join(lines))

    def check_tools(self):
        self.background('Checking developer tools', self.service.checks, self._tools_done)

    def _tools_done(self, records):
        rows = [f"{r['name']:15} {r['status']:14} {r['details']}" for r in records]
        self.check_result.set_text('\n'.join(rows))

    def show_logs(self, source):
        label = 'user' if source == 'user' else 'current boot'
        self.background('Reading ' + label + ' error logs', lambda: self.service.log(source),
                        self._logs_done)

    def _logs_done(self, text):
        self.log_view.get_buffer().set_text(text)
