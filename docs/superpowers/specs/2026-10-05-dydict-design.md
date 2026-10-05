# DyDict design

DyDict is a Linux translation popup. A hotkey runs the `dydict` command, a small window opens over the current desktop, and the translation appears in that window. The same command hides the window.

The app runs on any window manager, desktop, and distro that can run Python and GTK4. On compositors that offer the layer-shell protocol, the window is an overlay like an app launcher. Everywhere else it is a plain centered window.

## Names and paths

| Item | Value |
|---|---|
| Product name | DyDict |
| Command | `dydict` |
| Application id | `dydict` |
| Desktop file | `dydict.desktop` |
| Config | `~/.config/dydict/config.toml`, mode `0600` |
| Instance socket | `$XDG_RUNTIME_DIR/dydict.sock` |

If `XDG_CONFIG_HOME` or `XDG_RUNTIME_DIR` is set, those directories replace the defaults. If `XDG_RUNTIME_DIR` is unset, the socket path is `~/.cache/dydict/dydict.sock`.

## What the user does

1. The user binds `dydict` to a key in the desktop they already use.
2. They select text in any app, or they select nothing.
3. They press the key.
4. The popup opens, focused. Selected text is in the field and fully selected, so the next printable key replaces it. No selection leaves the field empty.
5. The translation appears under the field, with a direction line such as `English → Turkish` and an engine label, `online` or `offline`.
6. Enter copies the translation and hides the window. Esc hides the window and leaves the clipboard alone. A copy button copies the translation and leaves the window open.
7. Pressing the key while the window is open hides it. Pressing it again reads the selection again and shows the window.

Shift+Enter inserts a newline. Enter does not.

Editing the field waits 300 ms after the last change, then translates again. Opening with prefilled text translates at once and does not wait for that delay.

## Window

One GTK4 interface, two shells. The widgets are the same in both.

**Overlay.** Used when the compositor offers `zwlr_layer_shell_v1` and the `gtk4-layer-shell` typelib imports. Compositors that offer it include niri, Sway, Hyprland, River, and labwc. The window is on the top layer, 640 px wide, centered on the current monitor, with exclusive keyboard focus and no decorations. Esc hides it. Losing keyboard focus hides it.

**Plain window.** Used on GNOME, on X11, when the typelib is missing, and when the user passes `--floating`. The window is undecorated, 640 px wide, and centered on the current monitor. Losing focus hides it.

The result area scrolls. The window grows with the content up to 480 px tall. The text field shows two lines.

The window appears before the translation request returns. The result area fills in when the answer arrives.

## Single instance

The first `dydict` binds the socket and stays running after the window hides, so the next key press skips process startup. A second `dydict` connects, writes `toggle\n`, and exits.

- Visible window: hide it.
- Hidden window: read the selection, show the window, translate.
- Two processes start together: the one that binds the socket is the server. The other becomes the client.
- The client cannot connect: it prints an error and exits. It does not open a second window.

## Selection and copy

Reading the selection happens when the window is shown. The wait is capped at 200 ms. A timeout, a non-text result, a missing tool, or an error yields an empty field. The popup still opens.

| Session | Tool | Read | Write |
|---|---|---|---|
| Wayland (`WAYLAND_DISPLAY` set) | `wl-clipboard` | `wl-paste --primary --no-newline --type text/plain` | `wl-copy` |
| X11 | `xclip`, otherwise `xsel` | primary selection | clipboard selection |

When both `WAYLAND_DISPLAY` and `DISPLAY` are set, DyDict uses the Wayland tools.

`prepare_query` trims the text and keeps at most 2,000 characters. Longer input is cut, and the direction line says the text was shortened. An empty result clears the translation and sends no request. The function lives in `selection` so the tests can call it without GTK. The window runs every selection and every edit through it.

Enter and the copy button copy a translation only. They do nothing when the result is empty or an error, and Enter then leaves the window open. Copy writes the translation text. If the copy tool is missing, the result area says it could not copy, and Enter does not hide the window.

## Languages

The user sets a main language and a second language in the popup. They are ISO 639-1 codes. The v1 list is fixed:

`en`, `tr`, `de`, `fr`, `es`, `it`, `pt`, `nl`, `pl`, `ru`, `uk`, `sv`, `da`, `fi`, `nb`, `cs`, `ro`, `hu`, `el`, `bg`, `ar`, `he`, `hi`, `zh`, `ja`, `ko`, `vi`, `id`, `fa`, `th`.

The settings UI shows the English name of each code. The rest of the interface is English.

A missing file, a file that is not valid TOML, or a file whose known keys cannot be read loads every default: main `tr`, second `en`. The popup still opens. An unknown language code, or a main language equal to the second, resets both language keys to those defaults. A URL whose scheme is not `http` or `https` resets `online_url`. A `timeout_ms` that is not an integer of at least 1 resets `timeout_ms`. Every other valid key is kept. The two languages must differ. Save stays disabled while they are the same, and a line in the settings says they must differ.

### Direction

An offline detector (`lingua`) is built from the v1 list only.

The direction-line examples below use the defaults, Turkish and English.

| Detection | Source sent to the engine | Target | Direction line |
|---|---|---|---|
| Confidence at least 0.50 and the language is the main language | main | second | `Turkish → English` |
| Confidence at least 0.50 and the language is anything else | detected code | main | `German → Turkish` |
| Confidence under 0.50, no result, or the detector raises | `auto` | main | `Auto → Turkish` |

A string shorter than two characters after trimming uses the `auto` row. It still sends a request when it is not empty.

The swap control exchanges the two concrete codes currently shown and translates again. The exchange lasts until the user edits the field. Swap does not change the saved languages. Swap is disabled when the source is `auto`.

## Engines

Online runs first. Offline runs only after online fails.

**Online.** An HTTP POST to `<online_url>/translate` with a JSON body:

```json
{"q": "text", "source": "en", "target": "tr", "format": "text"}
```

`api_key` is included only when the configured key is non-empty. `source` is `auto` in the uncertain row above. The URL scheme must be `http` or `https`. The timeout is `timeout_ms` (default 2500). Success is HTTP 200 and a string `translatedText`. A timeout, a connection error, a bad scheme, a non-200 status, or a body without `translatedText` is failure.

The client is the Python standard library. Requests run off the UI thread. Each edit bumps a generation counter. A response whose generation is no longer current is discarded.

**Offline.** Argos Translate for the same source and target. `auto` is not a valid Argos source. When the source is `auto` and online failed, offline is skipped and the result area shows the online error.

Argos packages are directional. The download action installs both directions of the source and target that just failed, when both codes are in the v1 list. German detected with main Turkish downloads German → Turkish and Turkish → German. Packages go to the Argos user directory. The app does not download a package by itself.

| Outcome | What the popup shows |
|---|---|
| Online succeeds | Translation, label `online` |
| Online fails, offline package installed, source is concrete | Offline translation, label `offline` |
| Online fails, package missing, source is concrete | The online error, plus an offer to download both directions of that source and target |
| Online fails, source is `auto` | The online error, no download offer |
| Download fails | The download error. No automatic retry |
| Empty field | Empty result, no request |

The popup stays open for every failure row.

## Settings

A settings control in the popup edits the main language, the second language, the server URL, and the API key, then writes `config.toml`, including `timeout_ms`:

| Key | Default |
|---|---|
| `main_language` | `tr` |
| `second_language` | `en` |
| `online_url` | `https://libretranslate.com` |
| `online_api_key` | empty |
| `timeout_ms` | `2500` |

The API key field hides its contents. Save creates the config directory if needed, writes the file, and sets mode `0600`. The new values apply to the next translation immediately.

`timeout_ms` is in the file so it can be changed by hand. The settings UI does not show it.

## Project layout

```
pyproject.toml
README.md
data/dydict.desktop
dydict/
  __init__.py
  __main__.py
  app.py
  window.py
  shell.py
  selection.py
  detect.py
  engines.py
  config.py
  settings_view.py
tests/
  test_direction.py
  test_engines.py
  test_config.py
  test_selection.py
```

| Module | Responsibility |
|---|---|
| `app` | Process lifetime, socket, toggle |
| `window` | Field, direction line, result, copy, Enter, Esc, debounce, generation counter |
| `shell` | Overlay or plain window, centering, hide on focus loss |
| `selection` | Read primary selection, write clipboard |
| `detect` | Direction rule |
| `engines` | Online call, offline call, fallback, package download |
| `config` | Load, save, defaults |
| `settings_view` | The four visible settings |

`pyproject.toml` exposes the console script `dydict`. Python dependency floor is 3.11. Python packages are `lingua-language-detector`, `argostranslate`, and `tomli-w`. GTK4 and PyGObject come from the distro. `gtk4-layer-shell`, `wl-clipboard`, and `xclip` or `xsel` are optional.

The README gives install steps that are not tied to one distro, and example binds for niri, Sway, Hyprland, GNOME, KDE, and i3. The desktop file uses `Name=DyDict`, `Exec=dydict`, `Terminal=false`, `Type=Application`, `Categories=Utility;`, and `StartupNotify=false`.

## Testing

Unit tests use fakes. They open no window and make no network call.

- Direction: main language goes to the second language; any other detected language goes to the main language; low confidence, detector failure, and a one-character string use `auto` → main; swap exchanges concrete codes and stays off for `auto`.
- Engines: online success does not call offline; online failure with a concrete source calls offline; online failure with `auto` does not call offline; a missing package surfaces the download offer; a discarded stale generation does not replace the current result.
- Config: a missing file and a broken file both load the defaults; one bad key falls back as specified above and the other keys stay; a round-trip keeps the API key; Save refuses identical languages.
- Selection: a timeout and a missing tool both become an empty string. `prepare_query` trims and cuts input over 2,000 characters.

Manual check, once, on niri: the overlay opens from the bound key, a selection is translated, Enter copies and hides, Esc hides without copying. The same session run as `dydict --floating` centers a plain window and hides it when it loses focus.

## Out of scope

- Translation history
- A global shortcut grabbed by the app, including the global-shortcuts portal
- Dictionary senses
- More than two saved languages
- A translated interface
- Google or DeepL scraping
- A license file
- Quitting the resident process from the popup
