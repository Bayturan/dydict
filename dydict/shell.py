"""Layer-shell overlay, or a plain undecorated window."""

from __future__ import annotations

import os

WINDOW_WIDTH = 640


def use_overlay(floating: bool, typelib_ok: bool, protocol_ok: bool) -> bool:
    return (not floating) and typelib_ok and protocol_ok


def layer_shell_preload(current: str, library: str | None) -> str | None:
    """Put gtk4-layer-shell at the front of LD_PRELOAD.

    The library's Wayland shim only installs when it is loaded before
    libwayland. Python loads GTK first, so is_supported() stays false and
    the popup falls back to a plain window unless the process is re-executed
    with this preload.
    """
    if not library:
        return None
    parts = [part for part in current.replace(" ", ":").split(":") if part]
    if any(os.path.basename(part).startswith("libgtk4-layer-shell") for part in parts):
        return None
    return ":".join([library, *parts])


def layer_shell_library() -> str | None:
    import ctypes.util

    name = ctypes.util.find_library("gtk4-layer-shell")
    if not name:
        return None
    if os.path.isabs(name):
        return name if os.path.exists(name) else None
    for directory in ("/usr/lib", "/usr/lib64", "/usr/local/lib", "/lib"):
        path = os.path.join(directory, name)
        if os.path.exists(path):
            return path
    return name


def load_layer_shell():
    try:
        import gi

        gi.require_version("Gtk4LayerShell", "1.0")
        from gi.repository import Gtk4LayerShell
    except (ImportError, ValueError):
        return None
    return Gtk4LayerShell


def apply_shell(window, floating: bool) -> bool:
    layer = None if floating else load_layer_shell()
    protocol_ok = False
    if layer is not None:
        try:
            protocol_ok = bool(layer.is_supported())
        except Exception:
            protocol_ok = False
    if not use_overlay(floating, layer is not None, protocol_ok):
        window.set_decorated(False)
        bind_recenter(window, lambda height: center_plain_x11(window, height))
        return False
    layer.init_for_window(window)
    layer.set_namespace(window, "dydict")
    layer.set_layer(window, layer.Layer.TOP)
    layer.set_keyboard_mode(window, layer.KeyboardMode.EXCLUSIVE)
    layer.set_exclusive_zone(window, 0)
    layer.set_anchor(window, layer.Edge.TOP, True)
    layer.set_anchor(window, layer.Edge.LEFT, True)
    bind_recenter(window, lambda height: _center_on_output(window, layer, height))
    return True


def _pointer_monitor(window):
    display = window.get_display()
    seat = display.get_default_seat()
    device = seat.get_pointer() if seat is not None else None
    if device is None:
        return None
    surface, _x, _y = device.get_surface_at_position()
    if surface is None:
        return None
    return display.get_monitor_at_surface(surface)


def _window_monitor(window):
    display = window.get_display()
    native = window.get_native()
    surface = native.get_surface() if native is not None else None
    if surface is None:
        return None
    return display.get_monitor_at_surface(surface)


def _monitor(window):
    # Plain X11 only. The overlay path must not invent monitor 0.
    monitor = _pointer_monitor(window)
    if monitor is not None:
        return monitor
    monitors = window.get_display().get_monitors()
    if monitors.get_n_items():
        return monitors.get_item(0)
    return None


def _measured_height(window, height: int | None = None) -> int:
    if height is not None:
        return height if height > 0 else 0
    native = window.get_native()
    surface = native.get_surface() if native is not None else None
    if surface is not None and surface.get_height() > 0:
        return surface.get_height()
    value = window.get_height()
    return value if value > 0 else 0


def _overlay_margins(window, layer, monitor, height: int | None) -> None:
    # Margins are relative to the chosen monitor. geom.x is only for the X11 path.
    measured = _measured_height(window, height)
    if measured <= 0:
        return
    geom = monitor.get_geometry()
    layer.set_margin(window, layer.Edge.LEFT, max(0, (geom.width - WINDOW_WIDTH) // 2))
    layer.set_margin(window, layer.Edge.TOP, max(0, (geom.height - measured) // 2))


def _center_on_output(window, layer, height: int | None = None) -> None:
    pointer = _pointer_monitor(window)
    if pointer is not None:
        layer.set_monitor(window, pointer)
        _overlay_margins(window, layer, pointer, height)
        return
    monitor = _window_monitor(window)
    if monitor is None:
        return
    _overlay_margins(window, layer, monitor, height)


def center_plain_x11(window, height: int | None = None) -> None:
    """Center on X11. Wayland clients cannot place a plain toplevel; the compositor does."""
    try:
        import gi

        gi.require_version("GdkX11", "4.0")
        from gi.repository import GdkX11
    except (ImportError, ValueError):
        return
    native = window.get_native()
    surface = native.get_surface() if native is not None else None
    if not isinstance(surface, GdkX11.X11Surface):
        return
    monitor = _monitor(window)
    if monitor is None:
        return
    measured = _measured_height(window, height)
    if measured <= 0:
        return
    geom = monitor.get_geometry()
    surface.move(
        geom.x + max(0, (geom.width - WINDOW_WIDTH) // 2),
        geom.y + max(0, (geom.height - measured) // 2),
    )


def bind_recenter(window, place) -> None:
    seen = {"height": 0, "surface": None}

    def on_layout(_surface, _width, height):
        measured = int(height)
        if measured <= 0 or measured == seen["height"]:
            return
        seen["height"] = measured
        place(measured)

    def on_realize(_widget):
        native = window.get_native()
        surface = native.get_surface() if native is not None else None
        if surface is None or surface is seen["surface"]:
            return
        seen["surface"] = surface
        seen["height"] = 0
        surface.connect("layout", on_layout)

    window.connect("realize", on_realize)
    if window.get_realized():
        on_realize(window)
        measured = _measured_height(window)
        if measured > 0:
            seen["height"] = measured
            place(measured)
