from ai.person_detector import zone_aspect_warning


def test_warns_when_zone_was_drawn_16_9_but_camera_is_4_3():
    message = zone_aspect_warning((1280, 720), (640, 480))
    assert message is not None
    assert "1280x720" in message
    assert "640x480" in message


def test_no_warning_for_same_aspect_at_different_resolution():
    assert zone_aspect_warning((1920, 1080), (640, 360)) is None


def test_no_warning_when_saved_zone_size_is_unknown_or_invalid():
    assert zone_aspect_warning(None, (640, 480)) is None
    assert zone_aspect_warning((1280, 0), (640, 480)) is None
    assert zone_aspect_warning((1280, 720), (640, 0)) is None
