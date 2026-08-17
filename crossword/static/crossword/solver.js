"use strict";

const CW = window.CROSSWORD;
const ACROSS = "A";
const DOWN = "D";

const state = {
  cells: Array(CW.numRows * CW.numCols).fill(""),
  blocks: new Set(CW.blocks),
  cursor: 0,
  direction: ACROSS,
  checked: {}, // index -> "wrong" (permanent once set)
  indicators: {}, // index -> "correct" | "wrong" (cleared on next edit)
  completed: false,
};

const SVG_NS = "http://www.w3.org/2000/svg";
const svg = document.getElementById("grid");
const rows = CW.numRows;
const cols = CW.numCols;

const idx = (r, c) => r * cols + c;
const rowOf = (i) => Math.floor(i / cols);
const colOf = (i) => i % cols;
const isWhite = (r, c) =>
  r >= 0 && r < rows && c >= 0 && c < cols && !state.blocks.has(idx(r, c));

// --- Slot detection: a direct port of grid.py's slots(). Must stay in sync. ---
function computeSlots() {
  const out = [];
  let number = 0;
  for (let r = 0; r < rows; r++) {
    for (let c = 0; c < cols; c++) {
      if (!isWhite(r, c)) continue;
      const startsAcross = !isWhite(r, c - 1) && isWhite(r, c + 1);
      const startsDown = !isWhite(r - 1, c) && isWhite(r + 1, c);
      if (!startsAcross && !startsDown) continue;
      number += 1;
      const start = idx(r, c);
      if (startsAcross) {
        const indices = [];
        let cc = c;
        while (isWhite(r, cc)) indices.push(idx(r, cc++));
        out.push({ number, direction: ACROSS, start, indices });
      }
      if (startsDown) {
        const indices = [];
        let rr = r;
        while (isWhite(rr, c)) indices.push(idx(rr++, c));
        out.push({ number, direction: DOWN, start, indices });
      }
    }
  }
  return out;
}

// Number shown in a cell (if it begins any slot), as a map index -> number.
function cellNumbers(slots) {
  const m = {};
  for (const s of slots) m[s.start] = s.number;
  return m;
}

// Finds the slot running in `direction` that covers `cellIndex`, or
// undefined if no such slot exists.
function slotAt(cellIndex, direction, slots) {
  return slots.find(
    (s) => s.direction === direction && s.indices.includes(cellIndex)
  );
}

function slotKey(slot) {
  return slot ? `${slot.number}${slot.direction}` : null;
}

// Finds the slot adjacent to the cursor's current slot, walking forward or
// backward through the slots of the current direction. Falling off either
// end wraps into the other direction's list, so Tab/Shift+Tab can cycle
// through every slot in the puzzle. Returns null only if there are no slots.
function nextSlot(forward, slots) {
  const dirSlots = slots.filter((s) => s.direction === state.direction);
  if (!dirSlots.length) return null;
  const current = slotAt(state.cursor, state.direction, slots);
  if (!current) {
    const slot = forward ? dirSlots[0] : dirSlots[dirSlots.length - 1];
    return { slot, direction: state.direction };
  }
  const currentIdx = dirSlots.indexOf(current);
  if (forward) {
    if (currentIdx < dirSlots.length - 1) {
      return { slot: dirSlots[currentIdx + 1], direction: state.direction };
    }
    const otherDir = state.direction === ACROSS ? DOWN : ACROSS;
    const otherSlots = slots.filter((s) => s.direction === otherDir);
    return otherSlots.length ? { slot: otherSlots[0], direction: otherDir } : null;
  } else {
    if (currentIdx > 0) {
      return { slot: dirSlots[currentIdx - 1], direction: state.direction };
    }
    const otherDir = state.direction === ACROSS ? DOWN : ACROSS;
    const otherSlots = slots.filter((s) => s.direction === otherDir);
    return otherSlots.length
      ? { slot: otherSlots[otherSlots.length - 1], direction: otherDir }
      : null;
  }
}

// --- Persistence: solver progress is saved to localStorage per puzzle, so
// reloading or returning to a puzzle later restores exactly where the
// solver left off, including any errors they've been marked wrong for. ---
const STORAGE_KEY = `crossword-solver-${CW.pk}`;

function saveState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        cells: state.cells,
        checked: state.checked,
        indicators: state.indicators,
        completed: state.completed,
        cursor: state.cursor,
        direction: state.direction,
        timerSeconds,
      })
    );
  } catch (_) {
    // Storage unavailable (private browsing, quota, etc.) -- solving still
    // works, it just won't be restored next time.
  }
}

// Restores solver progress saved from a previous visit to this puzzle, if
// any. Returns true if state was restored, false if there was nothing to
// restore or it no longer matches this puzzle's grid (e.g. the puzzle was
// edited since), in which case the caller falls back to a fresh start.
function loadState() {
  let saved;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return false;
    saved = JSON.parse(raw);
  } catch (_) {
    return false;
  }
  if (!saved || !Array.isArray(saved.cells) || saved.cells.length !== rows * cols) {
    return false;
  }
  state.cells = saved.cells;
  state.checked = saved.checked || {};
  state.indicators = saved.indicators || {};
  state.completed = !!saved.completed;
  if (Number.isInteger(saved.cursor)) state.cursor = saved.cursor;
  if (saved.direction === ACROSS || saved.direction === DOWN) state.direction = saved.direction;
  if (Number.isInteger(saved.timerSeconds)) timerSeconds = saved.timerSeconds;
  return true;
}

// --- Rendering ---
// Rebuilds the whole SVG grid from scratch: cell rects, block styling,
// cursor/active-slot highlighting, cell numbers, entered letters, and the
// correct/wrong check indicators. Then refreshes the current-clue display
// and the across/down clue list. Called after every state change.
function render() {
  const slots = computeSlots();
  const numbers = cellNumbers(slots);
  const active = slotAt(state.cursor, state.direction, slots);
  const activeSet = new Set(active ? active.indices : []);

  svg.innerHTML = "";
  for (let i = 0; i < rows * cols; i++) {
    const r = rowOf(i);
    const c = colOf(i);
    const blocked = state.blocks.has(i);

    const rect = document.createElementNS(SVG_NS, "rect");
    rect.setAttribute("x", c);
    rect.setAttribute("y", r);
    rect.setAttribute("width", 1);
    rect.setAttribute("height", 1);
    const checkClass = !blocked && state.checked[i] ? " " + state.checked[i] : "";
    rect.setAttribute(
      "class",
      "cell" +
        (blocked ? " block" : "") +
        (!blocked && activeSet.has(i) ? " active" : "") +
        checkClass +
        (i === state.cursor ? " cursor" : "")
    );
    rect.dataset.index = i;
    svg.appendChild(rect);

    if (!blocked && numbers[i]) {
      const num = document.createElementNS(SVG_NS, "text");
      num.setAttribute("x", c + 0.05);
      num.setAttribute("y", r + 0.28);
      num.setAttribute("class", "cell-number");
      num.textContent = numbers[i];
      svg.appendChild(num);
    }
    if (!blocked && state.cells[i]) {
      const t = document.createElementNS(SVG_NS, "text");
      t.setAttribute("x", c + 0.5);
      t.setAttribute("y", r + 0.72);
      t.setAttribute("class", "cell-letter");
      t.setAttribute("text-anchor", "middle");
      t.textContent = state.cells[i];
      svg.appendChild(t);
    }
    if (!blocked && state.indicators[i]) {
      const ind = document.createElementNS(SVG_NS, "text");
      ind.setAttribute("x", c + 0.5);
      ind.setAttribute("y", r + 0.24);
      ind.setAttribute("class", "cell-indicator " + state.indicators[i]);
      ind.setAttribute("text-anchor", "middle");
      ind.textContent = state.indicators[i] === "correct" ? "" : "";
      svg.appendChild(ind);
    }
  }
  updateClueDisplay(active);
  renderClueList(slots, active);
  saveState();
}

// Shows the active slot's key (e.g. "1A") and its clue text (looked up from
// the server-supplied CW.clues map), or blanks both when there's no active
// slot.
function updateClueDisplay(active) {
  const slotEl = document.getElementById("current-slot");
  const clueEl = document.getElementById("clue-text");
  if (!active) {
    slotEl.textContent = "—";
    clueEl.textContent = "";
    return;
  }
  const key = slotKey(active);
  slotEl.textContent = key;
  clueEl.textContent = CW.clues[key] || "";
}

// Renders the across/down clue lists, highlighting whichever slot is
// currently active and flagging any slot the crossword itself didn't
// supply a clue for. Clicking an entry jumps the cursor to that slot.
function renderClueList(slots, active) {
  const across = document.getElementById("clue-list-across");
  const down = document.getElementById("clue-list-down");
  across.innerHTML = "";
  down.innerHTML = "";
  for (const s of slots) {
    const key = slotKey(s);
    const clue = CW.clues[key] || "";
    const li = document.createElement("li");
    li.value = s.number;
    li.textContent = clue || key;
    if (!clue) li.classList.add("no-clue");
    if (active && s.number === active.number && s.direction === active.direction) {
      li.classList.add("active");
    }
    li.addEventListener("click", () => {
      state.direction = s.direction;
      state.cursor = s.start;
      render();
      svg.focus();
    });
    (s.direction === ACROSS ? across : down).appendChild(li);
  }
}

// --- Navigation and editing ---
function setCursor(i) {
  if (i < 0 || i >= rows * cols) return;
  state.cursor = i;
  render();
}

// Moves the cursor to the next cell of the current slot, or -- once the
// slot's last cell is reached -- jumps to the start of the next slot, same
// as Tab/the next-slot-btn arrow. Reusing nextSlot() here (rather than
// re-deriving the traversal by walking raw grid cells) guarantees the two
// stay in agreement, including nextSlot()'s direction switch at the end of
// a direction's slot list.
function advance() {
  const slots = computeSlots();
  const current = slotAt(state.cursor, state.direction, slots);
  if (current) {
    const i = current.indices.indexOf(state.cursor);
    if (i < current.indices.length - 1) {
      state.cursor = current.indices[i + 1];
      return;
    }
  }
  const result = nextSlot(true, slots);
  if (result) {
    state.cursor = result.slot.start;
    state.direction = result.direction;
  }
}

// Moves the cursor one cell back along the current direction, but only onto
// an immediately adjacent white cell -- it does not skip blocks or wrap.
// Backspace uses this to step back within the current slot; when it can't
// move (already at the slot's start), the caller falls back to jumping to
// the previous slot entirely.
function retreat() {
  const r = rowOf(state.cursor);
  const c = colOf(state.cursor);
  if (state.direction === ACROSS && c - 1 >= 0 && isWhite(r, c - 1))
    state.cursor = idx(r, c - 1);
  else if (state.direction === DOWN && r - 1 >= 0 && isWhite(r - 1, c))
    state.cursor = idx(r - 1, c);
}

// Clicking a white cell moves the cursor there; clicking the cell that's
// already focused instead flips the typing direction. Clicks on blocks are
// ignored (the solver never places or removes blocks).
svg.addEventListener("click", (e) => {
  const target = e.target.closest(".cell");
  if (!target) return;
  const i = Number(target.dataset.index);
  if (state.blocks.has(i)) return;
  if (i === state.cursor) {
    state.direction = state.direction === ACROSS ? DOWN : ACROSS;
  }
  setCursor(i);
});

// Central keyboard/on-screen-keyboard handler shared by the physical
// keydown listener and the mobile keyboard buttons. Handles letter entry
// (with auto-advance and an auto-check once the grid is full), Backspace/
// Delete/Space clearing and moving, arrow-key navigation that skips blocks
// and wraps at grid edges, "." to flip direction, and Tab/Shift+Tab to jump
// slots. Returns true if the key was handled (so callers know whether to
// preventDefault), and does nothing once the puzzle is marked completed.
function handleKey(key, shiftKey = false) {
  if (state.completed) return false;
  const r = rowOf(state.cursor);
  const c = colOf(state.cursor);
  if (key === " ") {
    if (!state.blocks.has(state.cursor)) {
      state.cells[state.cursor] = "";
      delete state.indicators[state.cursor];
      clearMessage();
      advance();
      render();
    }
    return true;
  }
  if (key === "Backspace") {
    if (!state.blocks.has(state.cursor)) {
      playClick();
      if (state.cells[state.cursor]) {
        state.cells[state.cursor] = "";
        delete state.indicators[state.cursor];
        clearMessage();
      } else {
        const prev = state.cursor;
        retreat();
        if (state.cursor === prev) {
          const slots = computeSlots();
          const result = nextSlot(false, slots);
          if (result) {
            state.direction = result.direction;
            state.cursor = result.slot.indices[result.slot.indices.length - 1];
          }
        }
      }
      render();
    }
    return true;
  }
  if (key === "Delete") {
    if (!state.blocks.has(state.cursor)) {
      if (state.cells[state.cursor]) {
        state.cells[state.cursor] = "";
        delete state.indicators[state.cursor];
        clearMessage();
      } else {
        advance();
      }
      render();
    }
    return true;
  }
  if (key === "ArrowLeft") {
    let nc = c - 1;
    while (nc >= 0 && !isWhite(r, nc)) nc--;
    if (nc >= 0) {
      setCursor(idx(r, nc));
    } else {
      for (let dr = 1; dr <= rows; dr++) {
        const nr = (r - dr + rows) % rows;
        let lc = cols - 1;
        while (lc >= 0 && !isWhite(nr, lc)) lc--;
        if (lc >= 0) { setCursor(idx(nr, lc)); break; }
      }
    }
    return true;
  }
  if (key === "ArrowRight") {
    let nc = c + 1;
    while (nc < cols && !isWhite(r, nc)) nc++;
    if (nc < cols) {
      setCursor(idx(r, nc));
    } else {
      for (let dr = 1; dr <= rows; dr++) {
        const nr = (r + dr) % rows;
        let fc = 0;
        while (fc < cols && !isWhite(nr, fc)) fc++;
        if (fc < cols) { setCursor(idx(nr, fc)); break; }
      }
    }
    return true;
  }
  if (key === "ArrowUp") {
    let nr = r - 1;
    while (nr >= 0 && !isWhite(nr, c)) nr--;
    if (nr >= 0) {
      setCursor(idx(nr, c));
    } else {
      for (let dc = 1; dc <= cols; dc++) {
        const nc = (c - dc + cols) % cols;
        let lr = rows - 1;
        while (lr >= 0 && !isWhite(lr, nc)) lr--;
        if (lr >= 0) { setCursor(idx(lr, nc)); break; }
      }
    }
    return true;
  }
  if (key === "ArrowDown") {
    let nr = r + 1;
    while (nr < rows && !isWhite(nr, c)) nr++;
    if (nr < rows) {
      setCursor(idx(nr, c));
    } else {
      for (let dc = 1; dc <= cols; dc++) {
        const nc = (c + dc) % cols;
        let fr = 0;
        while (fr < rows && !isWhite(fr, nc)) fr++;
        if (fr < rows) { setCursor(idx(fr, nc)); break; }
      }
    }
    return true;
  }
  if (key === ".") {
    if (!state.blocks.has(state.cursor)) {
      state.direction = state.direction === ACROSS ? DOWN : ACROSS;
      render();
    }
    return true;
  }
  if (key === "Tab") {
    const slots = computeSlots();
    const result = nextSlot(!shiftKey, slots);
    if (result) {
      state.cursor = result.slot.start;
      state.direction = result.direction;
      render();
    }
    return true;
  }
  if (/^[a-zA-Z]$/.test(key)) {
    if (!state.blocks.has(state.cursor)) {
      playClick();
      state.cells[state.cursor] = key.toUpperCase();
      delete state.indicators[state.cursor];
      clearMessage();
      advance();
      render();
      autoCheckIfComplete();
    }
    return true;
  }
  return false;
}

svg.addEventListener("keydown", (e) => {
  if (handleKey(e.key, e.shiftKey)) e.preventDefault();
});

document.querySelectorAll(".kb-key").forEach((btn) => {
  btn.addEventListener("click", () => handleKey(btn.dataset.key));
});

// --- Check feature ---
// Asks the server whether the current cells are correct for `mode`
// ("letter"/"word"/"crossword") without ever revealing the right answer.
// When markWrong is true (manual Check button use), incorrect cells get a
// permanent "wrong" mark in state.checked (used for scoring) in addition to
// the transient indicator; autoCheckIfComplete() passes markWrong=false
// since it's just testing for a win, not penalizing mistakes twice. Returns
// the raw per-cell results, or null on a network error.
async function doCheck(mode, markWrong = true) {
  try {
    const resp = await fetch(CW.checkUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": CW.csrfToken,
      },
      body: JSON.stringify({
        mode,
        cells: state.cells,
        cursor: state.cursor,
        direction: state.direction,
      }),
    });
    if (!resp.ok) return null;
    const data = await resp.json();
    for (const { index, correct } of data.results) {
      if (state.cells[index] && markWrong) {
        state.indicators[index] = correct ? "correct" : "wrong";
        if (!correct) state.checked[index] = "wrong";
      }
    }
    render();
    return data.results;
  } catch (_) {
    return null;
  }
}

// True once every non-blocked cell holds a letter (regardless of whether
// those letters are correct) -- the trigger condition for auto-checking.
function isComplete() {
  for (let i = 0; i < rows * cols; i++) {
    if (!state.blocks.has(i) && !state.cells[i]) return false;
  }
  return true;
}

const msgEl = document.getElementById("completion-message");

function showMessage(text, type) {
  msgEl.textContent = text;
  msgEl.className = type;
  msgEl.hidden = false;
}

function clearMessage() {
  msgEl.hidden = true;
}

let soundEnabled = true;

const soundIcon = document.getElementById("sound-icon");
document.getElementById("sound-btn").addEventListener("click", () => {
  soundEnabled = !soundEnabled;
  soundIcon.classList.toggle("fa-volume-high", soundEnabled);
  soundIcon.classList.toggle("fa-volume-xmark", !soundEnabled);
});

const click_sound = document.getElementById('click-sound');
const tada_sound = document.getElementById('tada-sound');

// Plays the keyboard-click sound effect on each letter typed or backspaced,
// unless the user has muted sound. Resets currentTime first so rapid
// keystrokes retrigger the (very short) clip instead of playing into an
// already-finished element, which is a silent no-op.
function playClick() {
  if (soundEnabled) {
    click_sound.currentTime = 0;
    click_sound.play();
  }
}

// Plays the completion fanfare when the whole crossword is finished
// correctly.
function playTada() {
  if (soundEnabled) {
    tada_sound.currentTime = 0;
    tada_sound.play();
  }
}

// Once every cell is filled, silently checks the whole grid. If it's all
// correct, locks the puzzle (state.completed), stops the timer, plays the
// fanfare, hides the now-pointless check/reveal/sound controls, and shows a
// score based on the fraction of cells that were never marked wrong along
// the way. Otherwise just tells the solver something's wrong, without
// saying what -- they can keep editing.
async function autoCheckIfComplete() {
  if (!isComplete()) return;
  const results = await doCheck("crossword", false);
  if (!results) return;
  if (results.every((r) => r.correct)) {
    state.completed = true;
    clearInterval(timerInterval);
    playTada();
    document.getElementById("check-btn").closest(".check-dropdown").style.display = "none";
    document.getElementById("reveal-btn").closest(".check-dropdown").style.display = "none";
    document.getElementById("sound-btn").style.display = "none";
    const totalWhite = rows * cols - state.blocks.size;
    const wrongCount = Object.values(state.checked).filter(v => v === "wrong").length;
    const pct = Math.round((totalWhite - wrongCount) / totalWhite * 100);
    showMessage(`Crossword completed. You scored ${pct}%.`, "success");
    saveState();
  } else {
    showMessage("The crossword has some wrong answers.", "error");
  }
}

// --- Check dropdown ---
// Toggles the letter/word/crossword mode menu open/closed; picking an item
// runs doCheck() in that mode and closes the menu.
const checkBtn = document.getElementById("check-btn");
const checkMenu = document.getElementById("check-menu");

checkBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  checkMenu.hidden = !checkMenu.hidden;
});

checkMenu.addEventListener("click", (e) => {
  const li = e.target.closest("li[data-mode]");
  if (!li) return;
  checkMenu.hidden = true;
  doCheck(li.dataset.mode);
  svg.focus();
});

// --- Reveal feature ---
// After a confirmation prompt (reveal is destructive to the solver's own
// score), asks the server for the correct letters for `mode` and fills them
// in. Any cell that was blank or wrong gets permanently marked "wrong" in
// state.checked before being overwritten, so revealing can't be used to
// silently erase a mistake from the score; a correctly-guessed cell that's
// merely re-revealed keeps its existing indicator state. Finishes by
// re-running the completion check.
async function doReveal(mode) {
  const labels = { letter: "this letter", word: "this word", crossword: "the entire crossword" };
  if (!confirm(`Reveal ${labels[mode]}?`)) return;
  try {
    const resp = await fetch(CW.revealUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": CW.csrfToken },
      body: JSON.stringify({ mode, cursor: state.cursor, direction: state.direction }),
    });
    if (!resp.ok) return;
    const data = await resp.json();
    for (const { index, letter } of data.results) {
      if (!letter) continue;
      if (state.cells[index] !== letter) {
        // blank or wrong — count against score
        state.checked[index] = "wrong";
        state.cells[index] = letter;
      }
      delete state.indicators[index];
    }
    render();
    autoCheckIfComplete();
  } catch (_) {}
}

// --- Reveal dropdown --- (mirrors the check dropdown above, for doReveal())
const revealBtn = document.getElementById("reveal-btn");
const revealMenu = document.getElementById("reveal-menu");

revealBtn.addEventListener("click", (e) => {
  e.stopPropagation();
  revealMenu.hidden = !revealMenu.hidden;
});

revealMenu.addEventListener("click", (e) => {
  const li = e.target.closest("li[data-mode]");
  if (!li) return;
  revealMenu.hidden = true;
  doReveal(li.dataset.mode);
  svg.focus();
});

// Clicking anywhere outside the two dropdowns closes both (the buttons'
// own listeners stop propagation so their own clicks don't trigger this).
document.addEventListener("click", () => {
  checkMenu.hidden = true;
  revealMenu.hidden = true;
});

// Home/End jump the cursor to the first/last grid cell, unless a text
// input/textarea has focus (so it doesn't fight normal text editing).
document.addEventListener("keydown", (e) => {
  if (e.key === "Home" || e.key === "End") {
    if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
    e.preventDefault();
    setCursor(e.key === "Home" ? 0 : rows * cols - 1);
    svg.focus();
  }
});

// --- Timer ---
let timerSeconds = 0;
const timerEl = document.getElementById("timer");
const timerValueEl = document.getElementById("timer-value");
document.getElementById("timer-toggle").addEventListener("click", () => {
  const hidden = !timerEl.hidden;
  timerEl.hidden = hidden;
  document.getElementById("timer-toggle").textContent = hidden ? "Show" : "Hide";
});

// Formats a duration in seconds as HH:MM:SS.
function formatElapsed(totalSeconds) {
  const h = Math.floor(totalSeconds / 3600);
  const m = Math.floor((totalSeconds % 3600) / 60);
  const s = totalSeconds % 60;
  return (
    String(h).padStart(2, "0") + ":" +
    String(m).padStart(2, "0") + ":" +
    String(s).padStart(2, "0")
  );
}

// Ticks once a second. Stopped by autoCheckIfComplete() once the puzzle is
// solved. Saves state each tick too, so the elapsed time stays accurate on
// restore even if the solver hasn't typed anything for a while.
const timerInterval = setInterval(() => {
  timerSeconds++;
  timerValueEl.textContent = formatElapsed(timerSeconds);
  saveState();
}, 1000);

// Prev/next-slot buttons: on-screen equivalents of Shift+Tab / Tab, for
// mouse/touch users navigating between slots.
document.getElementById("prev-slot-btn").addEventListener("click", () => {
  const slots = computeSlots();
  const result = nextSlot(false, slots);
  if (result) {
    state.cursor = result.slot.start;
    state.direction = result.direction;
    render();
    svg.focus();
    playClick();
  }
});

document.getElementById("next-slot-btn").addEventListener("click", () => {
  const slots = computeSlots();
  const result = nextSlot(true, slots);
  if (result) {
    state.cursor = result.slot.start;
    state.direction = result.direction;
    render();
    svg.focus();
    playClick();
  }
});

// Restores progress saved from a previous visit to this puzzle, if any.
// Otherwise starts the solver on the first Across slot (if any) rather than
// cell 0, so opening a puzzle with a leading block doesn't leave the cursor
// stuck on a cell that isn't part of any slot.
if (loadState()) {
  timerValueEl.textContent = formatElapsed(timerSeconds);
  if (state.completed) {
    clearInterval(timerInterval);
    document.getElementById("check-btn").closest(".check-dropdown").style.display = "none";
    document.getElementById("reveal-btn").closest(".check-dropdown").style.display = "none";
    document.getElementById("sound-btn").style.display = "none";
  }
} else {
  const _initSlots = computeSlots();
  const _firstAcross = _initSlots.find((s) => s.direction === ACROSS);
  if (_firstAcross) {
    state.cursor = _firstAcross.start;
    state.direction = ACROSS;
  }
}
render();
svg.focus();
