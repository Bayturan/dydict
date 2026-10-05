from dydict.shell import WINDOW_WIDTH, _center_on_output, _monitor, use_overlay


class _Geom:
    def __init__(self, width, height, x=0, y=0):
        self.width = width
        self.height = height
        self.x = x
        self.y = y


class _Monitor:
    def __init__(self, name, width, height, x=0, y=0):
        self.name = name
        self.geom = _Geom(width, height, x, y)

    def get_geometry(self):
        return self.geom


class _Monitors:
    def __init__(self, items):
        self.items = items

    def get_n_items(self):
        return len(self.items)

    def get_item(self, index):
        return self.items[index]


class _Pointer:
    def __init__(self, surface):
        self.surface = surface

    def get_surface_at_position(self):
        return self.surface, 0, 0


class _Seat:
    def __init__(self, pointer):
        self.pointer = pointer

    def get_pointer(self):
        return self.pointer


class _Display:
    def __init__(self, pointer_surface, monitors, surface_monitors, seat=True):
        self.monitors = _Monitors(monitors)
        self.surface_monitors = surface_monitors
        self.seat = _Seat(_Pointer(pointer_surface)) if seat else None

    def get_default_seat(self):
        return self.seat

    def get_monitors(self):
        return self.monitors

    def get_monitor_at_surface(self, surface):
        return self.surface_monitors.get(surface)


class _Window:
    def __init__(self, display, surface):
        self.display = display
        self.surface = surface

    def get_display(self):
        return self.display

    def get_native(self):
        if self.surface is None:
            return None
        return type("Native", (), {"get_surface": lambda _self: self.surface})()

    def get_height(self):
        return 0


class _Layer:
    class Edge:
        LEFT = "left"
        TOP = "top"

    def __init__(self):
        self.monitor = None
        self.margins = {}

    def set_monitor(self, _window, monitor):
        self.monitor = monitor

    def set_margin(self, _window, edge, value):
        self.margins[edge] = value


def _outputs():
    pointer_surface = object()
    window_surface = object()
    pointer = _Monitor("pointer", 2000, 1200, x=1920, y=40)
    window = _Monitor("window", 1600, 900, x=800, y=10)
    output0 = _Monitor("zero", 800, 600, x=0, y=0)
    return pointer_surface, window_surface, pointer, window, output0


def test_overlay_only_when_the_compositor_and_library_agree():
    assert use_overlay(floating=False, typelib_ok=True, protocol_ok=True) is True
    assert use_overlay(floating=True, typelib_ok=True, protocol_ok=True) is False
    assert use_overlay(floating=False, typelib_ok=False, protocol_ok=True) is False
    assert use_overlay(floating=False, typelib_ok=True, protocol_ok=False) is False


def test_overlay_prefers_the_pointer_monitor_and_does_not_add_origin():
    pointer_surface, window_surface, pointer, window_monitor, output0 = _outputs()
    display = _Display(
        pointer_surface,
        [output0, pointer],
        {pointer_surface: pointer, window_surface: window_monitor},
    )
    window = _Window(display, window_surface)
    layer = _Layer()
    _center_on_output(window, layer, height=200)
    assert layer.monitor is pointer
    assert layer.margins == {
        "left": (pointer.geom.width - WINDOW_WIDTH) // 2,
        "top": (pointer.geom.height - 200) // 2,
    }


def test_overlay_uses_the_window_monitor_without_set_monitor():
    _pointer_surface, window_surface, _pointer, window_monitor, output0 = _outputs()
    display = _Display(
        None,
        [output0, window_monitor],
        {window_surface: window_monitor},
    )
    window = _Window(display, window_surface)
    layer = _Layer()
    _center_on_output(window, layer, height=100)
    assert layer.monitor is None
    assert layer.margins == {
        "left": (window_monitor.geom.width - WINDOW_WIDTH) // 2,
        "top": (window_monitor.geom.height - 100) // 2,
    }


def test_overlay_leaves_margins_alone_when_no_monitor_is_known():
    _pointer_surface, _window_surface, _pointer, _window_monitor, output0 = _outputs()
    display = _Display(None, [output0], {})
    window = _Window(display, None)
    layer = _Layer()
    _center_on_output(window, layer, height=180)
    assert layer.monitor is None
    assert layer.margins == {}
    assert _monitor(window) is output0
