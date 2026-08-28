"""Rulings on a measured master.

The numbers in these tests are from a real record run through the Rack:
-12.5 LUFS integrated, 4.2 LU range, -0.03 dBTP true peak. That last
figure is the whole reason this module exists - it looks harmless on a
peak meter and clips on every platform it is sent to.
"""
import audio_readiness as ar

REAL = {"measured_at": "2026-07-31T00:00:00", "integrated": -12.5,
        "lra": 4.2, "true_peak": -0.03, "bpm": 117.1,
        "bpm_confidence": 0.3, "key": "A minor", "key_fit": 0.79}


# --- the ceiling ---------------------------------------------------------

def test_a_peak_above_the_ceiling_is_a_problem():
    r = ar.true_peak_ruling(-0.03)
    assert r["level"] == "problem"
    assert "-1 dBTP" in r["headline"]
    # It must say how far to come down, not just that something is wrong.
    assert "0.97" in r["action"]


def test_a_safe_peak_passes():
    assert ar.true_peak_ruling(-1.5)["level"] == "ok"


def test_exactly_at_the_ceiling_is_not_over_it():
    assert ar.true_peak_ruling(-1.0)["level"] == "ok"


def test_a_very_low_peak_is_flagged_as_probably_a_rough_bounce():
    r = ar.true_peak_ruling(-12.0)
    assert r["level"] == "watch"


def test_an_unmeasured_peak_says_so_rather_than_passing():
    r = ar.true_peak_ruling(None)
    assert r["level"] == "unknown"      # never a silent pass


# --- loudness against real platform targets -----------------------------

def test_louder_than_every_target_is_reported_as_a_tradeoff_not_a_fault():
    r = ar.loudness_ruling(-8.0)
    assert r["level"] == "watch"
    assert "turn it down" in r["detail"]


def test_a_normal_master_sits_in_the_band():
    assert ar.loudness_ruling(-14.2)["level"] == "ok"


def test_a_quiet_master_with_headroom_is_flagged_as_raisable():
    # -22 LUFS peaking at -20 dBTP: plenty of room to come up.
    assert ar.loudness_ruling(-22.0, true_peak=-20.0)["level"] == "watch"


def test_quiet_but_already_peaking_is_the_worse_case():
    """Quiet average, peaks near the ceiling. Raising it would clip, so
    the useful finding is the gap itself - usually one stray transient
    holding the whole record down."""
    r = ar.loudness_ruling(-22.0, true_peak=-6.0)
    assert r["level"] == "problem"
    assert "no headroom" in r["headline"]
    assert "transient" in r["detail"]


def test_raising_a_quiet_master_that_would_clip_is_not_suggested():
    # Quiet, but with a peak so close to the ceiling that gain would
    # breach it. Suggesting "turn it up" there would be bad advice.
    r = ar.loudness_ruling(-20.0, true_peak=-0.5)
    assert "raise" not in (r.get("action") or "").lower()


# --- dynamic range -------------------------------------------------------

def test_a_flat_master_is_flagged():
    assert ar.range_ruling(1.5)["level"] == "watch"


def test_a_very_wide_range_suggests_an_unmastered_bounce():
    assert ar.range_ruling(20.0)["level"] == "watch"


def test_a_normal_range_passes():
    assert ar.range_ruling(4.2)["level"] == "ok"


# --- tempo and key: only quote what the detector was sure of ------------

def test_an_unconfident_tempo_is_hedged_not_stated():
    r = ar.tempo_key_ruling(117.1, 0.3, "A minor", 0.79)
    assert r["level"] == "watch"
    assert "not confident" in r["detail"] or "not confident" in r["headline"]


def test_a_confident_tempo_is_stated_plainly():
    r = ar.tempo_key_ruling(120.0, 0.9, "C major", 0.85)
    assert r["level"] == "ok"


# --- the whole assessment ------------------------------------------------

def test_the_real_track_is_caught():
    a = ar.assess(REAL)
    assert a["measured"] is True
    assert a["verdict"] == "problem"
    assert "dBTP" in a["summary"]


def test_never_measured_is_its_own_state():
    a = ar.assess(None)
    assert a["measured"] is False
    assert a["verdict"] == "unmeasured"
    # The distinction that matters: absent evidence is not a pass.
    assert a["verdict"] != "ok"


def test_a_clean_master_passes_cleanly():
    a = ar.assess({"measured_at": "x", "integrated": -14.1, "lra": 6.0,
                   "true_peak": -1.4})
    assert a["verdict"] == "ok"


def test_every_ruling_carries_its_evidence():
    for r in ar.assess(REAL)["rulings"]:
        if r["level"] != "unknown":
            assert r["evidence"], r["key"]


# --- what it contributes to Release Readiness ---------------------------

def test_an_unmeasured_master_scores_zero_not_a_default_pass():
    pts, mx, note = ar.readiness_points(None)
    assert pts == 0 and mx == 25
    assert "not measured" in note.lower()


def test_a_clipping_master_scores_near_zero():
    pts, _, note = ar.readiness_points(REAL)
    assert pts <= 5
    assert "dBTP" in note


def test_a_clean_master_scores_full():
    pts, mx, _ = ar.readiness_points(
        {"measured_at": "x", "integrated": -14.0, "lra": 5.0,
         "true_peak": -1.2})
    assert pts == mx


# --- the Twin's master read ---------------------------------------------

def test_the_twin_says_what_unlocks_the_master_read():
    import artist_os
    secs = artist_os.twin_report([], {}, [], [], analysis=None)
    read = [s for s in secs if s["title"] == "Master read"]
    assert read and read[0]["state"] == "awaiting"
    # It must name what to do, not just sit empty.
    assert "Rack" in read[0]["lines"][0]


def test_the_twin_reports_a_real_problem_on_the_master():
    import artist_os
    secs = artist_os.twin_report([], {}, [], [], analysis=REAL)
    read = [s for s in secs if s["title"] == "Master read"][0]
    assert read["state"] == "action"
    assert "dBTP" in " ".join(read["lines"])


def test_a_clean_master_reads_as_ready():
    import artist_os
    secs = artist_os.twin_report(
        [], {}, [], [], analysis={"measured_at": "x", "integrated": -14.0,
                                  "lra": 5.0, "true_peak": -1.3})
    read = [s for s in secs if s["title"] == "Master read"][0]
    assert read["state"] == "ready"


def test_the_planned_not_faked_placeholder_is_gone():
    """It said audio analysis was planned. It shipped, so the app should
    stop apologising for a capability it has."""
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    src = io.open(os.path.join(here, "artist_os.py"), encoding="utf8").read()
    assert "Hook / structure notes" not in src


# --- money cases are worked from the top down ---------------------------

def test_recovery_cases_sort_by_value_within_status():
    """The list is worked from the top down, so a $4 case must not sit
    above a $4,000 one just because it was opened more recently."""
    import inspect
    import db as store
    src = inspect.getsource(store.list_recovery_cases)
    assert "estimated_amount DESC" in src
    # Status still leads: an open $4 case beats a closed $4,000 one.
    assert src.index("CASE status") < src.index("estimated_amount DESC")


# --- the two copies of the platform targets must agree ------------------

def test_server_targets_match_the_ones_the_rack_shows():
    """loudness.js has its own TARGETS table and this module has another.

    Two copies of the same published figures can drift apart silently,
    and then the Rack tells an artist one thing while the readiness score
    is computed from another. This does not merge them - the browser
    needs its copy and the server needs its own - it just refuses to let
    them disagree.
    """
    import io
    import os
    import re
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = io.open(os.path.join(here, "static", "js", "loudness.js"),
                 encoding="utf8").read()
    block = js[js.index("TARGETS"):]
    block = block[:block.index("]")]
    js_targets = {}
    for name, lufs in re.findall(
            r'name:\s*"([^"]+)"[^}]*?lufs:\s*(-?\d+(?:\.\d+)?)', block):
        js_targets[name] = float(lufs)
    if not js_targets:                      # table shape changed
        for name, lufs in re.findall(
                r'\[\s*"([^"]+)"\s*,\s*(-?\d+(?:\.\d+)?)', block):
            js_targets[name] = float(lufs)

    assert js_targets, "could not read TARGETS out of loudness.js"
    for name, lufs in ar.PLATFORM_TARGETS:
        if name in js_targets:
            assert js_targets[name] == lufs, (
                "%s: loudness.js says %s, audio_readiness says %s"
                % (name, js_targets[name], lufs))


def test_the_hidden_peak_gap_is_stated_when_known():
    # -0.03 dBTP against -0.31 dBFS: 0.28 dB the meter never showed.
    r = ar.true_peak_ruling(-0.03, -0.31)
    assert "-0.31 dBFS" in r["detail"]
    assert "0.28 dB" in r["detail"]


def test_no_hidden_gap_claimed_when_sample_peak_is_unknown():
    r = ar.true_peak_ruling(-0.03)
    assert "peak meter reads" not in r["detail"]


# --- where the strongest section starts ---------------------------------

def test_the_hook_is_reported_as_a_timestamp():
    # The real track: 15s window at 34.9s, 30s window at 64.2s.
    r = ar.hook_ruling(64.2, 34.9, 0.07, 1.0)
    assert "1:04" in r["headline"] and "0:34" in r["headline"]


def test_a_snapped_hook_says_it_is_on_the_beat():
    r = ar.hook_ruling(64.2, 34.9, 0.07, 1.0)
    assert "downbeat" in r["detail"]


def test_an_unsnapped_hook_says_to_check_by_ear():
    """With no confident grid the window is energy-only, and saying so
    matters - a clip that starts mid-beat reads as a mistake."""
    r = ar.hook_ruling(64.2, None, None, 0.1)
    assert "by ear" in r["detail"]
    assert "downbeat" not in r["detail"]


def test_no_scan_is_its_own_state():
    r = ar.hook_ruling(None, None, None, None)
    assert r["level"] == "unknown"
    assert "Rack" in (r["action"] or "")


def test_an_unscanned_hook_does_not_fail_a_clean_master():
    """The hook is information, not a quality gate. A master with a safe
    peak and sensible loudness is still ok with no scan."""
    a = ar.assess({"measured_at": "x", "integrated": -14.0, "lra": 5.0,
                   "true_peak": -1.3})
    assert a["verdict"] == "ok"


def test_the_migration_covers_databases_that_predate_the_columns():
    """track_analysis shipped before these columns existed, so an install
    from earlier today has the table without them and CREATE TABLE IF NOT
    EXISTS will not help."""
    import inspect
    import db as store
    src = inspect.getsource(store.init_db)
    assert "ALTER TABLE track_analysis ADD COLUMN" in src
    for col in ("hook_15s", "hook_30s", "first_beat", "bar_seconds",
                "grid_confidence"):
        assert col in src, col


# --- the score that gates money decisions -------------------------------

def test_qualification_is_normalised_not_summed():
    """Every category is worth ten points, so a bare sum rescales the
    whole score each time one is added. That already happened once: a
    category added mid-session took the maximum to 110 and made every
    unlock threshold about nine percent easier without anyone touching a
    threshold."""
    import inspect
    import qualification
    src = inspect.getsource(qualification.calculate)
    assert "float(len(categories) * 10) * 100" in src
    assert "total = sum(pts for _, pts, _ in categories)" not in src


def test_qualification_reads_real_income():
    """It gates 'Catalog valuation review', 'Distribution rate
    improvement' and 'Upstream review' - three money decisions that had
    no money input at all."""
    import inspect
    import qualification
    src = inspect.getsource(qualification.calculate)
    assert "get_statement_rows" in src
    assert "Income on Record" in src


def test_no_statements_scores_zero_income_and_says_why():
    import inspect
    import qualification
    src = inspect.getsource(qualification.calculate)
    # Absent evidence is not a pass - same rule the master read follows.
    assert "income_pts = 0" in src
    assert "cannot speak to money" in src


# --- how far the biggest moment sits above the rest ---------------------

def test_a_normal_lift_passes():
    assert ar.peak_section_ruling(-8.0, -6.5, -12.5)["level"] == "ok"


def test_a_record_with_no_lift_is_flagged():
    r = ar.peak_section_ruling(-11.5, -10.0, -12.5)
    assert r["level"] == "watch"
    assert "only 1.0 LU" in r["headline"]


def test_one_towering_section_is_flagged():
    r = ar.peak_section_ruling(-3.0, -1.5, -12.5)
    assert r["level"] == "watch"
    assert "9.5 LU" in r["headline"]
    # It is the figure a delivery spec cares about, and says so.
    assert "delivery spec" in r["detail"]


def test_this_is_not_the_same_as_loudness_range():
    """LRA is the 10th-95th percentile spread and discards the extremes;
    short-term max IS the extreme. A record can be consistent by LRA and
    still have one section far above the body of it, so both rulings must
    be able to fire independently."""
    a = ar.assess({"measured_at": "x", "integrated": -12.5, "lra": 4.2,
                   "short_term_max": -3.0, "momentary_max": -1.5,
                   "true_peak": -1.5})
    levels = {r["key"]: r["level"] for r in a["rulings"]}
    assert levels["range"] == "ok"           # the spread is normal
    assert levels["peak_section"] == "watch"  # the extreme is not


def test_unmeasured_says_so_rather_than_scoring():
    assert ar.peak_section_ruling(None, None, -12.5)["level"] == "unknown"
    assert ar.peak_section_ruling(-6.0, None, None)["level"] == "unknown"


def test_the_evidence_quotes_both_figures():
    r = ar.peak_section_ruling(-8.0, -6.5, -12.5)
    assert "-8.0" in r["evidence"] and "-12.5" in r["evidence"]
    assert "momentary" in r["evidence"]
