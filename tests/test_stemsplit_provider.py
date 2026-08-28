"""Studio Split provider behaviour.

Both cases here come from watching real jobs run, not from reading the
docs. A test suite that only ever saw mocked happy paths passed the whole
time these were broken.
"""
import stemsplit_provider as sp


# --- naming a downloaded stem -------------------------------------------

def test_filename_follows_content_type():
    assert sp.stem_filename("vocals", "https://x/y", "audio/wav") \
        == "studio-split-vocals.wav"
    assert sp.stem_filename("drums", "https://x/y", "audio/mpeg") \
        == "studio-split-drums.mp3"
    assert sp.stem_filename("bass", "https://x/y", "audio/flac") \
        == "studio-split-bass.flac"


def test_filename_ignores_charset_suffix():
    assert sp.stem_filename("other", "https://x/y", "audio/wav; charset=binary") \
        == "studio-split-other.wav"


def test_filename_falls_back_to_the_url():
    # Unknown content type, but the presigned URL knows what it is.
    got = sp.stem_filename("vocals", "https://s3/x/vocals.flac?sig=abc",
                           "application/octet-stream")
    assert got == "studio-split-vocals.flac"


def test_filename_always_has_an_extension():
    # Nothing to go on at all still produces something openable, because
    # a file called "vocals" with no extension is the bug being fixed.
    got = sp.stem_filename("vocals", "https://s3/download?id=99", "")
    assert got.startswith("studio-split-vocals.")
    assert got.rsplit(".", 1)[-1].isalnum()


# --- completion is only believed when there is something to hand over ---

class _Api(object):
    """Stands in for the remote API across a sequence of polls."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = 0

    def __call__(self, method, path, **kw):
        self.calls += 1
        body = self.responses[min(self.calls - 1, len(self.responses) - 1)]
        return body, None


def _install(monkeypatch, api):
    monkeypatch.setattr(sp, "_call", api)
    sp._settling.clear()


def test_completed_with_no_stems_is_not_reported_as_finished(monkeypatch):
    # The exact response a real job returned: done, 100%, nothing to fetch.
    _install(monkeypatch, _Api([{"status": "COMPLETED", "progress": 100}]))
    out, err = sp.job_status("job1")
    assert err is None
    assert out["status"] == "PROCESSING"      # so the client keeps polling
    assert out["settling"] is True
    assert out["progress"] <= 99              # never claim 100 with nothing


def test_the_parked_source_survives_a_settling_job(monkeypatch):
    _install(monkeypatch, _Api([{"status": "COMPLETED", "progress": 100}]))
    sp._sources["job1"] = "/tmp/parked-source.wav"
    sp.job_status("job1")
    # Deleting it here would destroy the one thing a retry needs.
    assert sp._sources.get("job1") == "/tmp/parked-source.wav"
    sp._sources.pop("job1", None)


def test_completion_lands_once_the_urls_appear(monkeypatch):
    api = _Api([
        {"status": "COMPLETED", "progress": 100},                  # empty
        {"status": "COMPLETED", "progress": 100,
         "outputs": {"vocals": {"url": "https://s3/v.wav"},
                     "drums": {"url": "https://s3/d.wav"}}},
    ])
    _install(monkeypatch, api)
    first, _ = sp.job_status("job2")
    assert first["status"] == "PROCESSING"
    second, _ = sp.job_status("job2")
    assert second["status"] == "COMPLETED"
    assert second["stems"] == ["drums", "vocals"]
    assert "job2" not in sp._settling            # no leak once it lands


def test_settling_gives_up_rather_than_spinning_forever(monkeypatch):
    _install(monkeypatch, _Api([{"status": "COMPLETED", "progress": 100}]))
    sp.job_status("job3")
    # Rewind the clock past the grace window.
    sp._settling["job3"] -= sp.SETTLE_GRACE + 1
    out, _ = sp.job_status("job3")
    assert out["status"] == "COMPLETED"          # the truth, eventually
    assert out["stems"] == []


def test_a_job_with_stems_never_settles(monkeypatch):
    _install(monkeypatch, _Api([
        {"status": "COMPLETED", "progress": 100,
         "outputs": {"vocals": {"url": "https://s3/v.wav"}}}]))
    out, _ = sp.job_status("job4")
    assert out["status"] == "COMPLETED"
    assert sp._settling == {}


def test_failures_are_still_terminal(monkeypatch):
    _install(monkeypatch, _Api([{"status": "FAILED", "progress": 0}]))
    out, _ = sp.job_status("job5")
    assert out["status"] == "FAILED"             # not held open by settling


# --- separation modes ----------------------------------------------------

def test_modes_match_what_the_api_says_it_accepts():
    # Straight from the API's own rejection message:
    #   "Must be one of: VOCALS, INSTRUMENTAL, BOTH, FOUR_STEMS, SIX_STEMS"
    assert set(sp.MODES) == {"VOCALS", "INSTRUMENTAL", "BOTH",
                             "FOUR_STEMS", "SIX_STEMS"}


def test_six_stems_lifts_guitar_and_piano_out():
    six = sp.mode_stems("SIX_STEMS")
    four = sp.mode_stems("FOUR_STEMS")
    assert set(four) == {"vocals", "drums", "bass", "other"}
    assert set(six) - set(four) == {"guitar", "piano"}


def test_every_mode_partitions_the_record():
    """No mode may put a stem next to one that already contains it.

    "instrumental" is drums+bass+other again. A lane set holding both
    would play the record twice, which is an audio bug the user would
    hear before anyone read the code.
    """
    for name, mode in sp.MODES.items():
        stems = set(mode["stems"])
        if "instrumental" in stems:
            assert not (stems & {"drums", "bass", "other", "guitar", "piano"}), \
                "%s mixes instrumental with its own parts" % name
        assert len(stems) == len(mode["stems"]), "%s repeats a stem" % name


def test_unknown_mode_falls_back_rather_than_posting_it(monkeypatch):
    sent = {}

    def fake(method, path, payload=None, **kw):
        sent.update(payload or {})
        return {"id": "j1"}, None

    monkeypatch.setattr(sp, "_call", fake)
    sp.create_job("https://x/y.wav", "SEVEN_STEMS")
    # Posting an unknown enum earns a 400; fall back instead.
    assert sent["outputType"] == sp.DEFAULT_MODE


def test_requested_mode_is_the_one_sent(monkeypatch):
    sent = {}

    def fake(method, path, payload=None, **kw):
        sent.update(payload or {})
        return {"id": "j1"}, None

    monkeypatch.setattr(sp, "_call", fake)
    sp.create_job("https://x/y.wav", "SIX_STEMS")
    assert sent["outputType"] == "SIX_STEMS"


def test_mode_list_is_ordered_by_how_far_it_splits():
    counts = [m["count"] for m in sp.mode_list()]
    assert counts == sorted(counts)
    assert all(m.get("label") and m.get("note") for m in sp.mode_list())


def test_every_mode_stem_is_a_known_stem():
    for mode in sp.MODES.values():
        for stem in mode["stems"]:
            assert stem in sp.STEMS      # or the download route rejects it


# --- the flat response shape still parses -------------------------------

def test_outputs_reads_the_flat_shape(monkeypatch):
    _install(monkeypatch, _Api([
        {"status": "COMPLETED", "progress": 100,
         "vocalsUrl": "https://s3/v.wav", "drumsUrl": "https://s3/d.wav"}]))
    out, _ = sp.job_status("job6")
    assert out["stems"] == ["drums", "vocals"]
