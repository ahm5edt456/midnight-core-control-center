"""GTK4/Libadwaita backup UI. All filesystem work runs outside GTK's main loop."""
from threading import Thread

from gi.repository import Adw, GLib, Gtk

from midnight.services.backup_manager import BackupService, COMPONENTS


class BackupPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL, spacing=18)
        for setter in (
            self.set_margin_top, self.set_margin_bottom,
            self.set_margin_start, self.set_margin_end,
        ):
            setter(30)
        self.add_css_class('stage10-page')
        self.set_hexpand(True)
        self.service = BackupService()
        self.busy = False
        self.backups = []
        self.previewed_name = None
        self.previewed_manifest = None
        self.backup_checks = {}
        self.restore_checks = {}
        self.actions = []
        self._build()
        self.refresh()

    @staticmethod
    def _label(text, cls='stage10-muted'):
        label = Gtk.Label(label=str(text), xalign=0, wrap=True)
        label.set_selectable(cls in ('stage10-status', 'stage10-path'))
        label.add_css_class(cls)
        return label

    def _panel(self, name, description):
        panel = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12)
        panel.add_css_class('stage10-panel')
        panel.append(self._label(name, 'stage10-title'))
        panel.append(self._label(description))
        self.append(panel)
        return panel

    def _button(self, label, fn, cls=None):
        button = Gtk.Button(label=label)
        button.add_css_class(cls or 'stage10-button')
        button.connect('clicked', lambda *_: fn())
        self.actions.append(button)
        return button

    def _build(self):
        self.append(self._label('Backup & Restore', 'page-title'))
        self.append(self._label('Create private backups, preview content, and safely restore selected settings.'))

        create = self._panel('Create Backup',
            'Choose which user configuration files to include. No projects, caches, keys, or system files.')
        for name, (label, path, _) in COMPONENTS.items():
            check = Gtk.CheckButton(label=f'{label}  ·  ~/{path}')
            check.set_active(name != 'bash')
            create.append(check)
            self.backup_checks[name] = check
        create.append(self._button('Create Backup', self.create, 'stage10-primary'))

        storage = self._panel('Saved Backups',
            'Archives are stored locally in a private folder (no cloud upload).')
        self.location = self._label(str(self.service.storage), 'stage10-path')
        storage.append(self.location)
        controls = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.dropdown = Gtk.DropDown.new_from_strings(['No backups'])
        self.dropdown.set_hexpand(True)
        self.dropdown.connect('notify::selected', self._selection_changed)
        controls.append(self.dropdown)
        controls.append(self._button('Refresh List', self.refresh))
        controls.append(self._button('Verify & Preview', self.preview))
        storage.append(controls)

        restore = self._panel('Restore Selected Components',
            'Choose a backup and verify it first; then select the components to restore. '
            'Current settings are backed up automatically before replacement.')
        for name, (label, _path, _) in COMPONENTS.items():
            check = Gtk.CheckButton(label=label)
            check.set_sensitive(False)
            restore.append(check)
            self.restore_checks[name] = check
        restore.append(self._button('Restore Selected', self.confirm_restore, 'stage10-danger'))

        preview_title = self._label('Archive Preview', 'stage10-title')
        self.append(preview_title)
        scroll = Gtk.ScrolledWindow()
        scroll.set_min_content_height(140)
        scroll.set_max_content_height(260)
        scroll.set_propagate_natural_height(True)
        self.preview_text = Gtk.TextView()
        self.preview_text.set_editable(False)
        self.preview_text.set_cursor_visible(False)
        self.preview_text.set_monospace(True)
        self.preview_text.set_wrap_mode(Gtk.WrapMode.WORD_CHAR)
        self.preview_text.add_css_class('stage10-preview')
        scroll.set_child(self.preview_text)
        self.append(scroll)
        self._set_preview('Select a saved backup, then click Verify & Preview.')

        self.status = self._label('Ready. Backups stay on your device.', 'stage10-status')
        self.append(self.status)

    def _set_preview(self, text):
        self.preview_text.get_buffer().set_text(str(text))

    def _selection_changed(self, *_args):
        self.previewed_manifest = None
        self.previewed_name = None
        for check in self.restore_checks.values():
            check.set_active(False)
            check.set_sensitive(False)
        self._set_preview('Click Verify & Preview to inspect and validate the archive.')

    def _selected_name(self):
        index = self.dropdown.get_selected()
        if index >= len(self.backups):
            return None
        return self.backups[index]['name']

    def _thread_job(self, description, work, done):
        if self.busy:
            self.status.set_text('Another backup action is in progress.')
            return
        self.busy = True
        self.status.set_text(description + '…')
        for button in self.actions:
            button.set_sensitive(False)

        def worker():
            try:
                result = work()
                GLib.idle_add(self._complete, done, result, None)
            except Exception as error:
                GLib.idle_add(self._complete, done, None, str(error))

        Thread(target=worker, daemon=True).start()

    def _complete(self, done, result, error):
        self.busy = False
        for button in self.actions:
            button.set_sensitive(True)
        if error:
            self.status.set_text('Operation failed: ' + error)
        else:
            try:
                done(result)
            except Exception as exc:
                self.status.set_text('UI update failed: ' + str(exc))
        return GLib.SOURCE_REMOVE

    def refresh(self):
        if self.busy:
            return
        try:
            self.backups = self.service.list_backups()
            labels = [b['name'] for b in self.backups] or ['No backups']
            self.dropdown.set_model(Gtk.StringList.new(labels))
            self.dropdown.set_selected(0)
            self._selection_changed()
            self.status.set_text(f'{len(self.backups)} saved backup(s).')
        except Exception as exc:
            self.status.set_text('Cannot list backups: ' + str(exc))

    def create(self):
        chosen = [key for key, check in self.backup_checks.items() if check.get_active()]
        self._thread_job('Creating backup',
                         lambda: self.service.create_backup(chosen),
                         self._backup_done)

    def _backup_done(self, name):
        self.refresh()
        self.status.set_text('Backup created and saved: ' + name)

    def preview(self):
        name = self._selected_name()
        if not name:
            self.status.set_text('Select a backup first.')
            return
        self._thread_job('Checking archive integrity',
                         lambda: self.service.inspect(name),
                         lambda info: self._preview_done(name, info))

    def _preview_done(self, name, info):
        self.previewed_name = name
        self.previewed_manifest = info
        count = {}
        for entry in info['files']:
            count[entry['component']] = count.get(entry['component'], 0) + 1
        display = [
            'VERIFIED ARCHIVE',
            'Name: ' + name,
            'Created: ' + str(info['created_at']),
            'Label: ' + str(info['label']),
            '',
            'COMPONENTS:',
        ]
        for key in info['components']:
            if key in info['present']:
                display.append(f'  {COMPONENTS[key][0]}: {count.get(key, 0)} files')
            else:
                display.append(f'  {COMPONENTS[key][0]}: Not found when saved')
        display.extend(['', 'FILES (first 80):'])
        display.extend('  ' + entry['member'] for entry in info['files'][:80])
        if len(info['files']) > 80:
            display.append(f'  … and {len(info["files"]) - 80} more')
        self._set_preview('\n'.join(display))
        for key, check in self.restore_checks.items():
            available = key in info['present']
            check.set_sensitive(available)
            check.set_active(available and key != 'bash')
        self.status.set_text('Backup integrity verified. Choose components before restoring.')

    def confirm_restore(self):
        name = self._selected_name()
        if name is None or name != self.previewed_name or self.previewed_manifest is None:
            self.status.set_text('Verify & Preview the selected archive first.')
            return
        chosen = [key for key, check in self.restore_checks.items() if check.get_active()]
        if not chosen:
            self.status.set_text('Select at least one component for restoration.')
            return
        names = ', '.join(COMPONENTS[key][0] for key in chosen)
        dialog = Adw.AlertDialog.new(
            'Restore configuration?',
            'This will replace selected user settings:\n' + names + '\n\n'
            'A rescue backup of your CURRENT settings is saved before replacement. '
            'Close Neovim and Alacritty first.',
        )
        dialog.add_response('cancel', 'Cancel')
        dialog.add_response('restore', 'Restore Selected')
        dialog.set_default_response('cancel')
        dialog.set_close_response('cancel')
        dialog.set_response_appearance('restore', Adw.ResponseAppearance.DESTRUCTIVE)
        dialog.connect('response', self._restore_response, name, tuple(chosen))
        dialog.present(self.get_root())

    def _restore_response(self, _dialog, response, name, chosen):
        if response != 'restore':
            return
        self._thread_job(
            'Restoring selected settings',
            lambda: self.service.restore(name, chosen),
            lambda rescue: self._restore_done(rescue),
        )

    def _restore_done(self, rescue):
        self.refresh()
        self.status.set_text('Restore complete. Rescue backup: ' + rescue
                             + '. Restart affected apps to reload settings.')
