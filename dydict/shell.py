"""Layer-shell overlay, or a plain undecorated window."""

from __future__ import annotations

WINDOW_WIDTH = 640


def use_overlay(floating: bool, typelib_ok: bool, protocol_ok: bool) -> bool:
    return (not floating) and typelib_ok and protocol_ok


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
        return False
    layer.init_for_window(window)
    layer.set_namespace(window, "dydict")
    layer.set_layer(window, layer.Layer.TOP)
    layer.set_keyboard_mode(window, layer.KeyboardMode.EXCLUSIVE)
    layer.set_exclusive_zone(window, 0)
    layer.set_anchor(window, layer.Edge.TOP, True)
    layer.set_anchor(window, layer.Edge.LEFT, True)
    _center_on_output(window, layer)
    return True


def _monitor(window):
    display = window.get_display()
    seat = display.get_default_seat()
    device = seat.get_pointer() if seat is not None else None
    monitor = None
    if device is not None:
        surface, _x, _y = device.get_surface_at_position()
        if surface is not None:
            monitor = display.get_monitor_at_surface(surface)
    if monitor is None:
        monitors = display.get_monitors()
        if monitors.get_n_items():
            monitor = monitors.get_item(0)
    return monitor


def _center_on_output(window, layer) -> None:
    monitor = _monitor(window)
    if monitor is None:
        return
    layer.set_monitor(window, monitor)
    geom = monitor.get_geometry()
    height = max(window.get_allocated_height(), 120)
    layer.set_margin(window, layer.Edge.LEFT, max(0, (geom.width - WINDOW_WIDTH) // 2))
    layer.set_margin(window, layer.Edge.TOP, max(0, (geom.height - height) // 2))


def center_plain_x11(window) -> None:
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
    geom = monitor.get_geometry()
    height = max(window.get_height(), 120)
    surface.move(
        geom.x + max(0, (geom.width - WINDOW_WIDTH) // 2),
        geom.y + max(0, (geom.height - height) // 2),
    )
