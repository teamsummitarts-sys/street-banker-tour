/* Undo history: capped, coalescing, redo cleared on a new push. */
const E = require("../../static/js/lights-engine.js");
let fails = 0;
function ok(name, cond, detail) { console.log((cond ? "PASS  " : "FAIL  ") + name + (detail ? "   " + detail : "")); if (!cond) fails++; }

const H = E.makeHistory(50, 800);
ok("starts empty", !H.canUndo() && !H.canRedo() && H.size() === 0);
for (let i = 0; i < 60; i++) H.push("s" + i, "add", i * 1000);   // distinct gestures (1 s apart)
ok("capped at 50", H.size() === 50);
ok("undo returns the most recent snapshot", H.undo("cur") === "s59");
// redo hands back what undo took; undoing again returns to the pre-redo
// state, then continues down the stack.
ok("redo returns what undo took", H.redo("cur2") === "cur" && H.undo("x") === "cur2" && H.undo("y") === "s58");
// coalescing: same key within the window keeps the first snapshot only
const C = E.makeHistory(50, 800);
C.push("before-typing", "note:c1", 0);
const second = C.push("mid-typing", "note:c1", 300);
const third = C.push("later-typing", "note:c1", 700);
ok("pushes inside the window are merged", second === false && third === false && C.size() === 1);
ok("undo steps back over the whole gesture", C.undo("now") === "before-typing");
const D = E.makeHistory(50, 800);
D.push("a", "note:c1", 0); D.push("b", "note:c1", 900);
ok("a gap past the window starts a new step", D.size() === 2);
const K = E.makeHistory(50, 800);
K.push("a", "note:c1", 0); K.push("b", "inten:c1", 100);
ok("a different key is a new step even inside the window", K.size() === 2);
const R = E.makeHistory(50, 800);
R.push("a", "x", 0); R.undo("b"); ok("redo available after undo", R.canRedo());
R.push("c", "y", 2000); ok("a new push clears redo", !R.canRedo());
ok("undo on empty is null", E.makeHistory().undo("z") === null);

console.log(fails ? ("\n" + fails + " FAILED") : "\nall passed");
process.exit(fails ? 1 : 0);
