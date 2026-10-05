"""Settings box for the four visible preferences."""

from __future__ import annotations

from dydict.config import LANGUAGES, Config, settings_error


def build_settings(config: Config, on_save):
    import gi

    gi.require_version("Gtk", "4.0")
    from gi.repository import Gtk

    codes = list(LANGUAGES)
    names = [LANGUAGES[code] for code in codes]
    box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=6)
    main_drop = Gtk.DropDown.new_from_strings(names)
    second_drop = Gtk.DropDown.new_from_strings(names)
    main_drop.set_selected(codes.index(config.main_language))
    second_drop.set_selected(codes.index(config.second_language))
    url = Gtk.Entry()
    url.set_text(config.online_url)
    key = Gtk.PasswordEntry()
    key.set_text(config.online_api_key)
    note = Gtk.Label(label="", xalign=0)
    note.set_visible(False)
    save = Gtk.Button(label="Save")

    def selected_codes():
        return codes[main_drop.get_selected()], codes[second_drop.get_selected()]

    def refresh(*_args):
        main, second = selected_codes()
        error = settings_error(main, second, url.get_text().strip())
        note.set_visible(error is not None)
        note.set_text(error or "")
        save.set_sensitive(error is None)

    def save_clicked(_button):
        main, second = selected_codes()
        error = settings_error(main, second, url.get_text().strip())
        if error is not None:
            refresh()
            return
        on_save(Config(main, second, url.get_text().strip(), key.get_text(), config.timeout_ms))

    for widget in (main_drop, second_drop):
        widget.connect("notify::selected", refresh)
    url.connect("changed", refresh)
    save.connect("clicked", save_clicked)
    for child in (
        Gtk.Label(label="Main language", xalign=0),
        main_drop,
        Gtk.Label(label="Second language", xalign=0),
        second_drop,
        Gtk.Label(label="Server URL", xalign=0),
        url,
        Gtk.Label(label="API key", xalign=0),
        key,
        note,
        save,
    ):
        box.append(child)
    refresh()
    return box
