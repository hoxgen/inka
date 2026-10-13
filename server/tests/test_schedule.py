from inka_server.schedule import sleep_seconds, slot_index


def test_slot_index_advances_per_interval():
    assert slot_index(0, 600, 3, 0) == 0
    assert slot_index(599, 600, 3, 0) == 0
    assert slot_index(600, 600, 3, 0) == 1
    assert slot_index(1800, 600, 3, 0) == 0


def test_slot_index_offset():
    assert slot_index(0, 600, 3, 1) == 1
    assert slot_index(0, 600, 3, 5) == 2


def test_sleep_until_next_boundary_plus_margin():
    assert sleep_seconds(1000, 600) == 230


def test_sleep_minimum_is_60():
    assert sleep_seconds(1199, 600) == 60


def test_sleep_rounds_up_fraction():
    assert sleep_seconds(1000.4, 600) == 230
