from music_utils.duration import format_duration, parse_artist_list


def test_format_duration_basic():
    assert format_duration(65) == "1:05"


def test_format_duration_zero():
    assert format_duration(0) == "0:00"


def test_format_duration_over_an_hour():
    assert format_duration(3661) == "1:01:01"


def test_parse_artist_list_comma():
    assert parse_artist_list("Artist A, Artist B") == ["Artist A", "Artist B"]


def test_parse_artist_list_ampersand():
    assert parse_artist_list("Artist A & Artist B") == ["Artist A", "Artist B"]


def test_parse_artist_list_feat():
    assert parse_artist_list("Artist A feat. Artist B") == ["Artist A", "Artist B"]


def test_parse_artist_list_empty():
    assert parse_artist_list("") == []
