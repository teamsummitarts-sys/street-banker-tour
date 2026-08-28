"""Server-side conversion.

Most of these read the command rather than running it. That is
deliberate: the thing worth proving is that no value a user typed ever
reaches ffmpeg unchecked, and running the binary would prove the opposite
of nothing about it.
"""
import convert_engine as ce


def args_for(**kw):
    kw.setdefault("fmt", "mp3")
    return ce.build_args("in.wav", "out.x", kw.pop("fmt"), **kw)


# --- nothing user-typed reaches the command line ------------------------

def test_bitrate_outside_the_table_falls_back():
    # 999 is not on offer; the encoder must not be told to try it.
    args = args_for(bitrate=999)
    assert "-b:a" in args
    assert args[args.index("-b:a") + 1] == "320k"     # the format default


def test_rate_outside_the_table_is_dropped_entirely():
    assert "-ar" not in args_for(rate=7)


def test_channel_count_outside_the_table_is_dropped():
    assert "-ac" not in args_for(channels=9)


def test_every_argument_is_its_own_argv_entry():
    args = args_for(bitrate=320, rate=48000, channels=2)
    assert all(" " not in a for a in args if not a.endswith((".wav", ".x")))


def test_the_shell_is_never_asked_to_parse_anything():
    src = "in; rm -rf /.wav"
    args = ce.build_args(src, "out.mp3", "mp3")
    # The path travels as one argv entry, so the semicolon is just a
    # character in a filename rather than a command separator.
    assert src in args


# --- format behaviour ----------------------------------------------------

def test_lossless_formats_carry_no_bitrate():
    for fmt in ("flac", "alac", "wav", "aiff"):
        assert "-b:a" not in ce.build_args("i", "o", fmt), fmt


def test_bit_depth_only_applies_to_pcm():
    wav = ce.build_args("i", "o", "wav", depth=16)
    assert "pcm_s16le" in wav
    aiff = ce.build_args("i", "o", "aiff", depth=32)
    assert "pcm_f32be" in aiff          # AIFF is big-endian
    # A depth on a compressed format is meaningless and must be ignored.
    assert "-c:a" in ce.build_args("i", "o", "mp3", depth=16)
    assert "libmp3lame" in ce.build_args("i", "o", "mp3", depth=16)


def test_unknown_depth_leaves_the_format_default():
    assert "pcm_s24le" in ce.build_args("i", "o", "wav", depth=7)


def test_video_streams_are_dropped():
    # An m4a or webm input can carry cover art or video; -vn keeps it out
    # of an audio render.
    assert "-vn" in ce.build_args("i", "o", "mp3")


# --- the menu ------------------------------------------------------------

def test_lossless_formats_come_first():
    vals = [f["value"] for f in ce.format_list()]
    lossy = [i for i, f in enumerate(ce.format_list()) if f["lossy"]]
    lossless = [i for i, f in enumerate(ce.format_list()) if not f["lossy"]]
    assert max(lossless) < min(lossy)
    assert "mp3" in vals and "flac" in vals


def test_every_format_has_a_note_and_an_extension():
    for f in ce.format_list():
        assert f["note"] and f["ext"]
        assert f["lossy"] == ce.FORMATS[f["value"]]["lossy"]


def test_lossy_formats_offer_bitrates_and_lossless_do_not():
    for f in ce.format_list():
        assert bool(f["bitrates"]) == f["lossy"], f["value"]


# --- refusals ------------------------------------------------------------

def test_unknown_format_is_refused():
    out, name, err = ce.convert(b"x", "a.wav", "mp4v")
    assert out is None and "unknown format" in err


def test_empty_input_is_refused():
    out, name, err = ce.convert(b"", "a.wav", "mp3")
    assert out is None and err


def test_oversized_input_is_refused_before_any_work():
    big = b"\0" * (ce.MAX_BYTES + 1)
    out, name, err = ce.convert(big, "a.wav", "mp3")
    assert out is None and "MB" in err


def test_missing_encoder_is_reported_not_hidden(monkeypatch):
    monkeypatch.setattr(ce, "available", lambda: False)
    out, name, err = ce.convert(b"x", "a.wav", "mp3")
    assert out is None and "no encoder" in err


# --- what the rack page says depends on what the box can do -------------

def _rack_page(monkeypatch, has_encoder):
    """Render /rack with the encoder present or absent."""
    import app as app_mod
    import convert_engine
    monkeypatch.setattr(convert_engine, "available", lambda: has_encoder)
    application = app_mod.create_app()
    client = application.test_client()
    client.post("/login", data={"email": "demo@streetbanker.io",
                                "password": "sweep"})
    return client.get("/rack").get_data(as_text=True)


def test_without_an_encoder_the_page_promises_nothing_uploads(monkeypatch):
    page = _rack_page(monkeypatch, False)
    assert "Everything here runs in this tab; nothing uploads." in page
    # And it must not dangle formats it cannot produce.
    assert 'value="mp3"' not in page
    assert 'id="rk-cnv-brwrap"' not in page


def test_with_an_encoder_the_page_says_where_each_format_happens(monkeypatch):
    page = _rack_page(monkeypatch, True)
    assert "no browser gives a web page an MP3, FLAC or AAC encoder" in page
    assert "WAV and AIFF are written in this tab and never leave it" in page
    # The upload is disclosed before the button, not after.
    assert 'id="rk-cnv-where"' in page and 'id="rk-cnv-brwrap"' in page
    for fmt in ("mp3", "flac", "alac", "aac", "opus", "vorbis"):
        assert 'value="%s"' % fmt in page, fmt


# --- codecs that cannot store every sample rate -------------------------

def test_opus_is_never_asked_for_a_rate_it_cannot_store():
    # libopus takes 8/12/16/24/48 kHz only. Asking for 44.1 failed the
    # whole conversion, which is how this was found.
    args = ce.build_args("i", "o", "opus", rate=44100)
    assert "44100" not in args
    assert args[args.index("-ar") + 1] == "48000"


def test_opus_keeps_a_rate_it_can_store():
    assert ce.build_args("i", "o", "opus", rate=48000)[
        ce.build_args("i", "o", "opus", rate=48000).index("-ar") + 1] == "48000"


def test_the_substitution_is_reported_not_silent():
    rate, note = ce.resolve_rate("opus", 44100)
    assert rate == 48000 and note and "48" in note
    rate, note = ce.resolve_rate("opus", 48000)
    assert rate == 48000 and note is None


def test_other_codecs_keep_the_rate_they_were_given():
    for fmt in ("mp3", "flac", "wav", "aac", "vorbis"):
        args = ce.build_args("i", "o", fmt, rate=44100)
        assert args[args.index("-ar") + 1] == "44100", fmt


def test_high_rates_map_down_to_the_nearest_opus_can_do():
    assert ce.resolve_rate("opus", 96000)[0] == 48000
    assert ce.resolve_rate("opus", 22050)[0] == 24000


# --- the rack's knobs must stay reachable without a mouse ---------------
# Source-level guards. The knob is built in JS against a live AudioContext,
# so there is no cheap DOM harness for it here - but these are the exact
# lines whose quiet removal would put the controls back out of reach, and
# that is worth catching.

def _rackdsp():
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return io.open(os.path.join(here, "static", "js", "rackdsp.js"),
                   encoding="utf8").read()


def test_knobs_are_focusable_and_announce_themselves():
    js = _rackdsp()
    assert "wrap.tabIndex = 0" in js                    # Tab reaches it
    assert 'setAttribute("role", "slider")' in js       # and it says what it is
    for attr in ("aria-label", "aria-valuemin", "aria-valuemax",
                 "aria-valuenow", "aria-valuetext"):
        assert attr in js, attr


def test_knobs_respond_to_the_arrow_keys():
    js = _rackdsp()
    assert 'addEventListener("keydown"' in js
    for key in ("ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight",
                "PageUp", "PageDown", "Home", "End"):
        assert '"%s"' % key in js, key


def test_keyboard_does_not_hijack_browser_shortcuts():
    # Ctrl/Cmd/Alt combinations belong to the browser and to the Ctrl-K
    # palette, not to whichever knob happens to hold focus.
    assert "e.altKey || e.ctrlKey || e.metaKey" in _rackdsp()


def test_the_focus_ring_is_visible_and_round():
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    css = io.open(os.path.join(here, "templates", "rack.html"),
                  encoding="utf8").read()
    assert ".rk-knob:focus-visible" in css
    assert "border-radius: 50%" in css      # a square ring on a round knob
    # A mouse click should not leave a ring behind.
    assert ".rk-knob:focus:not(:focus-visible)" in css


def test_the_page_tells_people_the_keys_exist():
    # Nobody discovers arrow-key control by accident.
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    page = io.open(os.path.join(here, "templates", "rack.html"),
                   encoding="utf8").read()
    assert "Every knob in the rack takes the keyboard" in page


# --- the command palette has to be reachable without a Ctrl key ---------

def _base_html():
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return io.open(os.path.join(here, "templates", "base.html"),
                   encoding="utf8").read()


def test_the_palette_has_a_control_not_only_a_shortcut():
    page = _base_html()
    # Ctrl-K is not on a phone keyboard. Seventy destinations behind it
    # is the same as no way to reach them.
    assert 'id="sb-search"' in page
    assert 'aria-label="Search pages"' in page
    assert 'searchBtn.addEventListener("click"' in page


def test_the_palette_can_be_dismissed_by_touch():
    page = _base_html()
    assert 'id="cmdk-close"' in page          # a visible way out
    assert "if (e.target === box) { close(); }" in page   # and the backdrop


def test_keyboard_hints_do_not_show_where_there_is_no_keyboard():
    page = _base_html()
    # The arrow/enter hints and the esc chip are keyboard affordances.
    # Assert the affordance is desktop-only, not the exact grey - the
    # palette moved off gray-500 because it read at 4.1:1 on black.
    assert '<span class="hidden sm:inline"><kbd' in page
    assert '↑↓</kbd> move</span>' in page
    assert 'sm:inline' in page and 'esc</kbd>' in page


def test_the_two_header_buttons_are_thumb_sized():
    page = _base_html()
    # Both the search and the menu button, at 44px. Asserts the size, not
    # the whole class string - this broke twice on colour changes that had
    # nothing to do with whether a thumb can hit the button.
    import re
    boxes = re.findall(r'class="flex h-11 w-11 items-center justify-center[^"]*"',
                       page)
    assert len(boxes) == 2, "expected two 44px header buttons, found %d" % len(boxes)


# --- the rack's tooltips have to be reachable without hover -------------

def test_explain_mode_exists():
    """Forty-eight controls carry their only description in a title
    attribute. Hover does not exist on a phone, so that text was
    unreachable there - and it is sentences, not decoration."""
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    page = io.open(os.path.join(here, "templates", "rack.html"),
                   encoding="utf8").read()
    assert 'id="rk-explain"' in page
    assert 'aria-pressed="false"' in page          # it is a toggle
    assert ".rk-explain-note" in page              # and it has a style


def test_explain_is_generated_from_the_titles_themselves():
    """Not a hand-written list. A control added later must be covered
    without anyone remembering this feature exists."""
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = io.open(os.path.join(here, "static", "js", "rackdsp.js"),
                 encoding="utf8").read()
    assert 'querySelectorAll("[title]")' in js
    assert 'el.getAttribute("title")' in js
    # textContent, never innerHTML.
    assert "note.textContent = el.getAttribute" in js
    assert "note.innerHTML" not in js


def test_the_titles_survive_explain_mode():
    """A pointer user should keep their tooltips - explain mode adds a
    caption, it does not move the text out of the attribute."""
    import io
    import os
    here = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    js = io.open(os.path.join(here, "static", "js", "rackdsp.js"),
                 encoding="utf8").read()
    assert 'removeAttribute("title")' not in js
