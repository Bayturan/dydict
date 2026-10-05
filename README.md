# DyDict

DyDict is a translation popup. The command `dydict` opens it. Running the command again hides it.

Selected text is placed in the box. With no selection, the box is empty. Text in the main language is translated into the second language. Any other text is translated into the main language. An online LibreTranslate server is tried first. Argos Translate answers when the network request fails and the language package is installed.

## Install

GTK4 and PyGObject come from the distro. The Python packages install into a virtual environment that can see them.

Arch:

    sudo pacman -S gtk4 python-gobject wl-clipboard
    sudo pacman -S --asdeps gtk4-layer-shell

Debian or Ubuntu:

    sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 wl-clipboard gir1.2-gtk4layershell-1.0

Fedora:

    sudo dnf install python3-gobject gtk4 wl-clipboard gtk4-layer-shell

`gtk4-layer-shell` and `wl-clipboard` are optional. Without the layer-shell library, DyDict opens a plain window. On X11, install `xclip` or `xsel` instead of `wl-clipboard`.

    python -m venv --system-site-packages .venv
    .venv/bin/pip install -e ".[dev]"
    cp data/dydict.desktop ~/.local/share/applications/

## Use

Bind the command `dydict` in the desktop. DyDict does not grab a global key.

niri, in `binds`:

    Mod+T { spawn "dydict"; }

Sway:

    bindsym Mod4+t exec dydict

Hyprland:

    bind = SUPER, T, exec, dydict

i3:

    bindsym $mod+t exec dydict

GNOME: Settings, Keyboard, Custom Shortcuts, command `dydict`.

KDE: System Settings, Shortcuts, add the command `dydict`.

Enter copies the translation and hides the window. Esc hides it and leaves the clipboard alone. Shift+Enter inserts a newline. Swap flips the current direction until the text changes. Settings edits the main language, the second language, the server URL, and the API key.

`dydict --floating` forces the plain window.

## Config

`~/.config/dydict/config.toml`, or `$XDG_CONFIG_HOME/dydict/config.toml`.

    main_language = "tr"
    second_language = "en"
    online_url = "https://libretranslate.com"
    online_api_key = ""
    timeout_ms = 2500

The public server may require an API key. Point `online_url` at any LibreTranslate-compatible server. A DeepL address (`https://api-free.deepl.com` or `https://api.deepl.com`, including a full `/v2/translate` path) uses the DeepL API with the same key field.
