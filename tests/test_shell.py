from dydict.shell import use_overlay


def test_overlay_only_when_the_compositor_and_library_agree():
    assert use_overlay(floating=False, typelib_ok=True, protocol_ok=True) is True
    assert use_overlay(floating=True, typelib_ok=True, protocol_ok=True) is False
    assert use_overlay(floating=False, typelib_ok=False, protocol_ok=True) is False
    assert use_overlay(floating=False, typelib_ok=True, protocol_ok=False) is False
