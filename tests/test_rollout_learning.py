"""What past rollouts converted.

The discipline being tested is mostly refusal: this module must stay
quiet until it has enough traffic to mean something. An artist who
reweights their whole campaign because one platform got four lucky
clicks is worse off than one who was told nothing.
"""
import rollout_learning as rl


def _mk(name, vid, utm_source="", medium="rollout"):
    return {"id": vid, "name": name, "utm_source": utm_source,
            "utm_medium": medium}


def _world(variants, stats):
    return ([{"id": "c1"}], lambda cid: variants, lambda cid: stats)


# --- reading platform and phase back out of the variant name ------------

def test_parses_platform_and_phase():
    assert rl._parse("rollout_tiktok_teaser_2026-08-05") == ("tiktok", "teaser")


def test_parses_a_platform_that_contains_underscores():
    # instagram_reels is the case that breaks a naive split.
    assert rl._parse("rollout_instagram_reels_launch_2026-08-05") == \
        ("instagram_reels", "launch")


def test_ignores_names_that_are_not_rollout_variants():
    assert rl._parse("summer-promo") == (None, None)
    assert rl._parse("") == (None, None)
    assert rl._parse(None) == (None, None)


# --- refusing to speak on thin evidence ---------------------------------

def test_says_nothing_on_a_handful_of_clicks():
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_x_teaser_2026-08-02", "v2", "x")]
    stats = {"v1": {"page_view": 8, "service_click": 6},
             "v2": {"page_view": 5, "service_click": 0}}
    rep = rl.report(*_world(variants, stats))
    # A 75% click rate on 8 visits is noise, not a finding.
    assert rep["platforms"]["finding"] is None
    assert rep["platforms"]["confident"] is False
    assert "Not enough traffic" in rep["platforms"]["note"]


def test_says_nothing_when_only_one_platform_has_traffic():
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_x_teaser_2026-08-02", "v2", "x")]
    stats = {"v1": {"page_view": 200, "service_click": 40},
             "v2": {"page_view": 3, "service_click": 0}}
    rep = rl.report(*_world(variants, stats))
    assert rep["platforms"]["finding"] is None
    assert "Only one" in rep["platforms"]["note"]


def test_says_nothing_when_platforms_are_close():
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_x_teaser_2026-08-02", "v2", "x")]
    stats = {"v1": {"page_view": 100, "service_click": 20},
             "v2": {"page_view": 100, "service_click": 19}}
    rep = rl.report(*_world(variants, stats))
    assert rep["platforms"]["finding"] is None
    assert "clearly ahead" in rep["platforms"]["note"]


# --- and speaking when the evidence is real -----------------------------

def test_names_a_winner_when_the_gap_is_real():
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_x_teaser_2026-08-02", "v2", "x")]
    stats = {"v1": {"page_view": 200, "service_click": 60},
             "v2": {"page_view": 200, "service_click": 20}}
    rep = rl.report(*_world(variants, stats))
    f = rep["platforms"]["finding"]
    assert f and f["key"] == "tiktok"
    assert f["lift"] > 0
    assert "tiktok" in rep["platforms"]["note"]


def test_ranks_by_rate_not_by_volume():
    """The platform with the most clicks is usually just the one with the
    most posts."""
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_x_teaser_2026-08-02", "v2", "x")]
    stats = {"v1": {"page_view": 1000, "service_click": 100},   # 10%
             "v2": {"page_view": 100, "service_click": 40}}     # 40%
    rep = rl.report(*_world(variants, stats))
    assert rep["platforms"]["rows"][0]["key"] == "x"


def test_totals_accumulate_across_separate_rollouts():
    variants = [_mk("rollout_tiktok_teaser_2026-08-01", "v1", "tiktok"),
                _mk("rollout_tiktok_launch_2026-09-01", "v2", "tiktok")]
    stats = {"v1": {"page_view": 50, "service_click": 10},
             "v2": {"page_view": 50, "service_click": 10}}
    plat, _ = rl.gather(*_world(variants, stats))
    assert plat["tiktok"]["visits"] == 100
    assert plat["tiktok"]["posts"] == 2


def test_non_rollout_variants_are_left_out():
    variants = [_mk("summer-promo", "v1", "instagram", medium="social")]
    stats = {"v1": {"page_view": 500, "service_click": 200}}
    plat, _ = rl.gather(*_world(variants, stats))
    assert plat == {}


# --- what it hands the rest of the app ----------------------------------

def test_platform_suggestion_falls_back_when_nothing_is_measured():
    rep = {"platforms": {"confident": False, "rows": []}}
    got = rl.suggested_platforms(rep, ["tiktok", "x"], ["tiktok"])
    assert got == ["tiktok"]          # a new account behaves as before


def test_platform_suggestion_uses_what_was_measured():
    rep = {"platforms": {"confident": True, "rows": [
        {"key": "tiktok", "enough": True}, {"key": "x", "enough": False}]}}
    got = rl.suggested_platforms(rep, ["tiktok", "x"], ["x"])
    assert got == ["tiktok"]


def test_next_action_stays_silent_without_a_finding():
    assert rl.next_action_line({"platforms": {}, "phases": {}}) is None


def test_next_action_says_something_true_when_there_is_a_finding():
    line = rl.next_action_line(
        {"platforms": {"finding": {"key": "tiktok", "lift": 42}}, "phases": {}})
    assert "tiktok" in line and "42" in line
