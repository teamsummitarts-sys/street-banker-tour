"""The Artist EQ actually runs in a browser-like runtime.

Every other test in this repo is server-side. That is how the EQ shipped
broken: renaming two keys in `artist_eq_config.py` closed a real Jinja
hazard, kept the whole Python suite green, and left the console dead on
the live site. The browser reads the same config as JSON, so `lane.keys`
became `undefined` and `.reduce` threw on every render — no slider moved
the plan, no preset did anything, and nothing anywhere went red.

So these tests execute `static/js/artist-eq.js` in Node against the exact
JSON the homepage embeds, and drive the two interactions that matter:
moving a fader and clicking a preset.

The last test is the one that keeps the others honest. It re-introduces
the original bug into a copy of the script and asserts the harness
*fails*. Without it this file could quietly rot into something that
passes no matter what the script does.

Limits, stated plainly: Node with a hand-built DOM stub is not a browser.
There is no layout, no CSS, no painting, no real event dispatch. These
tests prove the logic runs and recomputes. They say nothing about whether
the result looks right.
"""
import json
import os
import shutil
import subprocess
import tempfile

import pytest

from artist_eq_config import get_artist_eq_config

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
HARNESS = os.path.join(HERE, "js", "artist_eq_harness.js")
SCRIPT = os.path.join(ROOT, "static", "js", "artist-eq.js")

NODE = os.environ.get("SB_NODE_BIN") or shutil.which("node") or shutil.which("node.exe")

# Skipping is the right default — not every machine running the suite has
# Node. But a silent skip removes this protection without anyone noticing,
# which is the exact failure this file exists to prevent. Set
# SB_REQUIRE_JS_TESTS=1 wherever the suite is expected to be complete, and
# a missing Node becomes a failure instead of a shrug.
_REQUIRED = os.environ.get("SB_REQUIRE_JS_TESTS") == "1"

needs_node = pytest.mark.skipif(
    NODE is None and not _REQUIRED,
    reason="node is not on PATH; set SB_REQUIRE_JS_TESTS=1 to make this fail "
           "instead of skip, or SB_NODE_BIN to point at a node binary")


def test_the_javascript_runtime_is_available_when_it_is_required():
    """Guard the guard: if this suite is meant to cover the browser, say so.

    Without this, the whole file skips on a machine with no Node and the
    run still reports all-green — which is how the EQ shipped broken in
    the first place.
    """
    if not _REQUIRED:
        pytest.skip("SB_REQUIRE_JS_TESTS is not set; JS coverage is optional here")
    assert NODE, (
        "SB_REQUIRE_JS_TESTS=1 but no node binary was found. The Artist EQ "
        "runtime tests are the only thing in this suite that executes the "
        "page's JavaScript; without them a config rename can kill the "
        "console with every Python test still passing.")


def _run(script_path):
    """Execute the harness and return its parsed result."""
    if not NODE or not os.path.exists(NODE):
        pytest.fail("no usable node binary (%r) — cannot execute the page's "
                    "JavaScript" % (NODE,))
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False,
                                     encoding="utf-8") as handle:
        # The same object the template embeds as #sbeq-config, so a
        # serialization change is caught here too.
        json.dump(get_artist_eq_config(), handle)
        config_path = handle.name
    try:
        proc = subprocess.run(
            [NODE, HARNESS, script_path, config_path],
            capture_output=True, text=True, timeout=90, cwd=ROOT)
        assert proc.returncode == 0, (
            "the harness itself failed to run:\n%s" % (proc.stderr or "")[:2000])
        return json.loads(proc.stdout)
    finally:
        os.unlink(config_path)


@pytest.fixture(scope="module")
def result():
    return _run(SCRIPT)


@needs_node
def test_the_script_loads_without_throwing(result):
    assert result["loadError"] is None, (
        "artist-eq.js threw on load: %s\n"
        "The console is dead on the page whenever this fails."
        % result["loadError"])
    assert result["loaded"]


@needs_node
def test_the_server_rendered_plan_is_present_before_any_interaction(result):
    """The panel is painted by the server, so it must never start empty."""
    initial = result["initial"]
    assert initial["score"], "no readiness score after load"
    assert initial["lane"], "no recommended lane after load"


@needs_node
def test_moving_a_fader_recomputes_the_plan(result):
    assert result["dragError"] is None, (
        "moving a fader threw: %s" % result["dragError"])
    assert result["dragged"], "no input handler is bound to the faders"
    assert result["afterDrag"] != result["initial"], (
        "the plan did not change when a fader moved: %r"
        % (result["afterDrag"],))


@needs_node
def test_choosing_a_preset_recomputes_the_plan(result):
    assert result["presetError"] is None, (
        "clicking a preset threw: %s" % result["presetError"])
    assert result["presetApplied"], "no click handler is bound to the presets"
    assert result["afterPreset"] != result["afterDrag"], (
        "preset %r did not change the plan: %r"
        % (result.get("presetId"), result["afterPreset"]))


@needs_node
def test_the_readouts_the_panel_promises_are_all_written(result):
    """Score, band, lane and setup time — the four the section shows."""
    final = result["afterPreset"]
    for field in ("score", "band", "lane", "setup"):
        assert final[field], "%s was never written to the panel" % field


@needs_node
def test_this_harness_would_catch_the_bug_that_shipped():
    """The control. Re-introduce the original defect; the harness must fail.

    `l.keys` -> `l.channel_keys` against a config that still carries
    `keys` is precisely what went live. If the harness reports success on
    that, every test above is worthless and this one says so.
    """
    source = open(SCRIPT, encoding="utf-8").read()
    broken = source.replace("l.keys.reduce", "l.channel_keys.reduce")
    assert broken != source, (
        "could not re-introduce the known bug — artist-eq.js no longer "
        "contains `l.keys.reduce`, so this control needs rewriting against "
        "whatever replaced it")

    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False,
                                     encoding="utf-8") as handle:
        handle.write(broken)
        broken_path = handle.name
    try:
        outcome = _run(broken_path)
    finally:
        os.unlink(broken_path)

    assert outcome["loadError"] is not None, (
        "the harness reported success on a script with the known crash in "
        "it — it is not actually exercising the lane calculation")
    assert "reduce" in outcome["loadError"], outcome["loadError"]
    assert not outcome["initial"]["score"], (
        "a plan was still produced by the broken script; the harness is "
        "reading something other than the live render path")
