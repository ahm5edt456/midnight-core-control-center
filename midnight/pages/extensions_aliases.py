"""Midnight Core: GNOME extensions and read-only/managed Bash aliases."""
from threading import Thread

from gi.repository import GLib, Gtk

from midnight.services.extensions import ExtensionService
from midnight.services.aliases import AliasService


def title(text, style='muted'):
    label = Gtk.Label(label=text, xalign=0, wrap=True)
    label.add_css_class(style)
    return label


def base_page(heading, subtitle):
    page = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=18)
    page.set_margin_top(32)
    page.set_margin_bottom(32)
    page.set_margin_start(32)
    page.set_margin_end(32)
    page.append(title(heading, 'page-title'))
    page.append(title(subtitle))
    return page


def panel(heading):
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=10)
    box.add_css_class('stage8-panel')
    box.append(title(heading, 'section-title'))
    return box


def reset_list(listbox):
    child = listbox.get_first_child()
    while child is not None:
        next_child = child.get_next_sibling()
        listbox.remove(child)
        child = next_child


class ExtensionsPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.service = ExtensionService()
        self.records = []
        self.search_index = {}
        self.busy = False
        self.undo = None
        self.set_hexpand(True)
        self.append(base_page(
            'GNOME Extensions',
            'Enable, disable, search, and open preferences for installed extensions. '
            'Enabled does not always mean running: GNOME may require a session restart.',
        ))
        self.content = self.get_first_child()
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.search = Gtk.SearchEntry()
        self.search.set_placeholder_text('Search extensions...')
        self.search.set_hexpand(True)
        self.search.connect('search-changed', lambda *_: self._filter())
        toolbar.append(self.search)
        reload_btn = Gtk.Button(label='Refresh')
        reload_btn.connect('clicked', lambda *_: self.refresh())
        toolbar.append(reload_btn)
        self.content.append(toolbar)

        self.status = title('Reading installed GNOME extensions...', 'stage8-status')
        self.content.append(self.status)
        self.group = panel('Installed Extensions')
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class('stage8-list')
        self.group.append(self.listbox)
        self.content.append(self.group)
        self.refresh()

    def _background(self, work, on_success, action='Working'):
        if self.busy:
            return
        self.busy = True
        self.status.set_text(action + '...')

        def task():
            try:
                result = work()
            except Exception as exc:
                message = str(exc)
                GLib.idle_add(self._finished, on_success, None, message)
            else:
                GLib.idle_add(self._finished, on_success, result, None)

        Thread(target=task, daemon=True).start()

    def _finished(self, on_success, result, error):
        self.busy = False
        if error:
            self.status.set_text('Error: ' + error)
        else:
            on_success(result)
        return GLib.SOURCE_REMOVE

    def refresh(self):
        self._background(self.service.list_extensions, self._show, 'Loading extensions')

    def _show(self, records):
        self.records = records
        reset_list(self.listbox)
        self.search_index.clear()
        for ext in records:
            row = Gtk.ListBoxRow()
            item = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=12)
            item.set_margin_top(12)
            item.set_margin_bottom(12)
            item.set_margin_start(12)
            item.set_margin_end(12)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.set_hexpand(True)
            labels.append(title(ext.name, 'stage8-entry-name'))
            subtitle = ext.uuid + (' · System' if ext.system else ' · User')
            labels.append(title(subtitle, 'stage8-id'))
            if ext.description:
                labels.append(title(ext.description[:125]))
            item.append(labels)
            state = title('Enabled' if ext.enabled else 'Disabled',
                          'stage8-on' if ext.enabled else 'stage8-off')
            state.set_valign(Gtk.Align.CENTER)
            item.append(state)
            pref = Gtk.Button(label='Preferences')
            pref.set_valign(Gtk.Align.CENTER)
            pref.connect('clicked', lambda _, uuid=ext.uuid: self._prefs(uuid))
            item.append(pref)
            toggle = Gtk.Button(label='Disable' if ext.enabled else 'Enable')
            toggle.set_valign(Gtk.Align.CENTER)
            toggle.add_css_class('stage8-toggle')
            toggle.connect('clicked', lambda _, uuid=ext.uuid, old=ext.enabled:
                           self._toggle(uuid, old))
            item.append(toggle)
            row.set_child(item)
            self.search_index[row] = (ext.name + ' ' + ext.uuid + ' ' + ext.description).casefold()
            self.listbox.append(row)
        self._filter()
        self.status.set_text(f'{len(records)} extensions found. '
                             'Buttons affect your current user session.')

    def _filter(self):
        needle = self.search.get_text().casefold().strip()
        child = self.listbox.get_first_child()
        while child is not None:
            child.set_visible(needle in self.search_index.get(child, ''))
            child = child.get_next_sibling()

    def _toggle(self, uuid, currently_enabled):
        if self.busy:
            return

        def work():
            self.service.set_enabled(uuid, not currently_enabled)
            return self.service.list_extensions()

        def done(records):
            self._show(records)
            self.status.set_text(
                f'{uuid}: requested {"enable" if not currently_enabled else "disable"}. '
                'GNOME may need a session restart to load it.'
            )

        self._background(work, done, 'Updating ' + uuid)

    def _prefs(self, uuid):
        if self.busy:
            return
        self._background(
            lambda: self.service.open_preferences(uuid),
            lambda _: self.status.set_text(f'Opened preferences for {uuid} '
                                           '(when provided by the extension).'),
            'Opening preferences',
        )


class AliasesPage(Gtk.Box):
    def __init__(self):
        super().__init__(orientation=Gtk.Orientation.VERTICAL)
        self.service = AliasService()
        self.original = None
        self.search_index = {}
        self.set_hexpand(True)
        self.append(base_page(
            'Bash Alias Manager',
            'Existing aliases are read-only. New aliases live in a separate managed file. '
            'Commands are saved as text; this application never executes them.',
        ))
        self.content = self.get_first_child()
        toolbar = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
        self.search = Gtk.SearchEntry()
        self.search.set_hexpand(True)
        self.search.set_placeholder_text('Search aliases or commands...')
        self.search.connect('search-changed', lambda *_: self._filter())
        toolbar.append(self.search)
        refresh = Gtk.Button(label='Refresh')
        refresh.connect('clicked', lambda *_: self.reload())
        toolbar.append(refresh)
        self.content.append(toolbar)

        self.summary = title('', 'stage8-status')
        self.content.append(self.summary)
        self.group = panel('Bash Aliases')
        self.listbox = Gtk.ListBox()
        self.listbox.set_selection_mode(Gtk.SelectionMode.NONE)
        self.listbox.add_css_class('stage8-list')
        self.group.append(self.listbox)
        self.content.append(self.group)

        editor = panel('Add / Edit Managed Alias')
        editor.append(title('Shell code is not run on Save. It executes only if you '
                            'invoke that alias later in Bash. Review all commands carefully.'))
        self.alias_name = Gtk.Entry()
        self.alias_name.set_placeholder_text('Alias name, e.g. build42')
        self.alias_command = Gtk.Entry()
        self.alias_command.set_placeholder_text('Command, e.g. make -j4')
        editor.append(self.alias_name)
        editor.append(self.alias_command)
        buttons = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=8)
        for text, callback in [
            ('Save Alias', self.save), ('New Alias', self.new),
            ('Delete Selected', self.delete), ('Restore Previous', self.restore),
        ]:
            button = Gtk.Button(label=text)
            button.connect('clicked', callback)
            buttons.append(button)
        editor.append(buttons)
        self.content.append(editor)
        self.status = title('Reload Bash (source ~/.bashrc) after saving.', 'stage8-status')
        self.content.append(self.status)
        self.reload()

    def reload(self, *_):
        try:
            records = self.service.list_aliases()
        except Exception as exc:
            self.status.set_text('Unable to read aliases: ' + str(exc))
            return
        reset_list(self.listbox)
        self.search_index.clear()
        for alias in records:
            row = Gtk.ListBoxRow()
            outer = Gtk.Box(orientation=Gtk.Orientation.HORIZONTAL, spacing=10)
            outer.set_margin_top(8)
            outer.set_margin_bottom(8)
            outer.set_margin_start(12)
            outer.set_margin_end(12)
            labels = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=3)
            labels.set_hexpand(True)
            labels.append(title(alias.name, 'stage8-entry-name'))
            command = title(alias.command, 'stage8-command')
            command.set_selectable(True)
            labels.append(command)
            labels.append(title(alias.source + (' · editable' if alias.editable else ' · read-only'), 'stage8-id'))
            outer.append(labels)
            action = Gtk.Button(label='Edit' if alias.editable else 'View')
            action.connect('clicked', lambda _, a=alias: self.select_alias(a))
            outer.append(action)
            row.set_child(outer)
            self.search_index[row] = (alias.name + ' ' + alias.command + ' ' + alias.source).casefold()
            self.listbox.append(row)
        self._filter()
        managed = sum(1 for record in records if record.editable)
        self.summary.set_text(f'{len(records)} aliases · {managed} managed · '
                              f'{len(records) - managed} read-only')

    def _filter(self):
        needle = self.search.get_text().casefold().strip()
        child = self.listbox.get_first_child()
        while child is not None:
            child.set_visible(needle in self.search_index.get(child, ''))
            child = child.get_next_sibling()

    def select_alias(self, alias):
        self.original = alias.name if alias.editable else None
        self.alias_name.set_text(alias.name)
        self.alias_command.set_text(alias.command)
        self.alias_name.set_sensitive(alias.editable)
        self.alias_command.set_sensitive(alias.editable)
        self.status.set_text('Editing managed alias.' if alias.editable else
                             'This alias is read-only. Click New Alias to add your own.')

    def new(self, *_):
        self.original = None
        self.alias_name.set_sensitive(True)
        self.alias_command.set_sensitive(True)
        self.alias_name.set_text('')
        self.alias_command.set_text('')
        self.alias_name.grab_focus()
        self.status.set_text('Enter a name and a command; Save writes to managed-aliases.bash.')

    def save(self, *_):
        if not self.alias_name.get_sensitive():
            self.status.set_text('Read-only alias. Click New Alias instead.')
            return
        try:
            backup = self.service.save(
                self.alias_name.get_text().strip(),
                self.alias_command.get_text(),
                original=self.original,
            )
            self.original = self.alias_name.get_text().strip()
            self.reload()
            self.status.set_text(f'Saved. Backup: {backup.name}. Source ~/.bashrc '
                                 'in any existing shell to refresh aliases.')
        except Exception as exc:
            self.status.set_text('Save failed: ' + str(exc))

    def delete(self, *_):
        if not self.original:
            self.status.set_text('Select Edit on a managed alias to delete it.')
            return
        try:
            self.service.delete(self.original)
            self.new()
            self.reload()
            self.status.set_text('Managed alias deleted. Source ~/.bashrc in existing shells.')
        except Exception as exc:
            self.status.set_text('Delete failed: ' + str(exc))

    def restore(self, *_):
        try:
            self.service.restore_previous()
            self.new()
            self.reload()
            self.status.set_text('Previous managed aliases restored. Source ~/.bashrc.')
        except Exception as exc:
            self.status.set_text('Restore failed: ' + str(exc))
