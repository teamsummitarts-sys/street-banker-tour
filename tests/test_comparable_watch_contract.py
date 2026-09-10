def test_comparable_watch_public_contract_markers():
    """Static contract: the feature remains evidence-first and weekly-oriented."""
    from reach import comparable_watch

    assert comparable_watch.SIGNAL == "SIGNAL"
    assert comparable_watch.PROMOTED == "PROMOTED"
    assert comparable_watch.DISMISSED == "DISMISSED"
    assert comparable_watch.due.__defaults__ == (7,)
