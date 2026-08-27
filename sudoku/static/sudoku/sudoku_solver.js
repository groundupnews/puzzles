"use strict";

// Rules carried over from the sudoku on the main GroundUp site: a cell
// holds either one committed digit or a set of pencilled notes, digits
// clash with their row, column and box, and the puzzle is done when every
// cell holds a single digit with no clashes. The mistake count, the hint
// and the undo stack lean on the stored solution.

const SD = window.SUDOKU;
const SIZE = 9;
const CELLS = SIZE * SIZE;
const STORAGE_KEY = `sudoku-solver-${SD.pk}`;
const MAX_MISTAKES = 3;
const UNDO_LIMIT = 60;

// Row, column and box membership for each cell, worked out once.
const PEERS = (() => {
  const rows = [], cols = [], boxes = [];
  for (let i = 0; i < SIZE; i++) { rows.push([]); cols.push([]); boxes.push([]); }
  for (let i = 0; i < CELLS; i++) {
    const r = Math.floor(i / SIZE), c = i % SIZE;
    rows[r].push(i);
    cols[c].push(i);
    boxes[Math.floor(r / 3) * 3 + Math.floor(c / 3)].push(i);
  }
  // Flattened and de-duplicated: every cell that constrains this one.
  return Array.from({ length: CELLS }, (_, i) => {
    const r = Math.floor(i / SIZE), c = i % SIZE;
    const box = Math.floor(r / 3) * 3 + Math.floor(c / 3);
    return [...new Set([...rows[r], ...cols[c], ...boxes[box]])].filter((j) => j !== i);
  });
})();

const given = SD.puzzle.split("").map((ch) => ch !== "0");
const firstBlank = Math.max(0, SD.puzzle.indexOf("0"));

const state = {
  cells: SD.puzzle.split("").map((ch) => (ch === "0" ? "" : ch)),
  notes: {}, // cell index -> sorted digit string, e.g. "247"
  cursor: firstBlank,
  notesMode: false,
  mistakes: 0,
  revealed: {}, // cells the hint gave away
  completed: false,
};

// Snapshots taken before each change, so a misclick costs a keystroke
// rather than a restart.
const undoStack = [];

function snapshot() {
  undoStack.push(
    JSON.stringify({
      cells: state.cells,
      notes: state.notes,
      mistakes: state.mistakes,
      revealed: state.revealed,
    })
  );
  if (undoStack.length > UNDO_LIMIT) undoStack.shift();
}

function undo() {
  const previous = undoStack.pop();
  if (!previous) return;
  const saved = JSON.parse(previous);
  state.cells = saved.cells;
  state.notes = saved.notes;
  state.mistakes = saved.mistakes;
  state.revealed = saved.revealed;
  state.completed = isSolved();
  paint();
  saveState();
}

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved) return;
    // Givens always come from the puzzle, never from storage, so a saved
    // game can't contradict the grid it was played on.
    if (Array.isArray(saved.cells) && saved.cells.length === CELLS) {
      saved.cells.forEach((v, i) => {
        if (!given[i]) state.cells[i] = v || "";
      });
    }
    state.notes = saved.notes || {};
    state.cursor = Number.isInteger(saved.cursor) ? saved.cursor : state.cursor;
    state.notesMode = !!saved.notesMode;
    state.mistakes = saved.mistakes || 0;
    state.revealed = saved.revealed || {};
    state.completed = !!saved.completed;
  } catch (_) {
    // Corrupt or unavailable storage: start a fresh game rather than fail.
  }
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (_) {
    // Storage unavailable -- play still works, it just won't be restored.
  }
}

// True if the committed digit in `i` repeats among the cells that
// constrain it. Notes are deliberately ignored: they're speculative, and
// letting one mark a neighbour -- a given, even -- as wrong would punish
// the solver for thinking out loud.
function clashes(i) {
  const value = state.cells[i];
  return !!value && PEERS[i].some((j) => state.cells[j] === value);
}

function isSolved() {
  return state.cells.every((v, i) => v && !clashes(i));
}

function placed(digit) {
  return state.cells.filter((v) => v === digit).length;
}

// --- The board is built once and repainted in place ------------------------

let cellEls = [];

function buildBoard() {
  const board = document.getElementById("sd-board");
  board.innerHTML = "";
  cellEls = [];
  for (let i = 0; i < CELLS; i++) {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "sd-cell";
    cell.dataset.index = i;
    if (given[i]) cell.classList.add("is-given");

    const value = document.createElement("span");
    value.className = "sd-value";

    // Nine fixed slots, so a pencilled 4 always sits where a 4 belongs.
    const notes = document.createElement("span");
    notes.className = "sd-notes";
    for (let d = 1; d <= SIZE; d++) notes.appendChild(document.createElement("span"));

    cell.append(value, notes);
    cell.addEventListener("click", () => select(i));
    board.appendChild(cell);
    cellEls.push({ cell, value, notes });
  }
}

function paint() {
  const cursorRow = Math.floor(state.cursor / SIZE);
  const cursorCol = state.cursor % SIZE;
  const cursorValue = state.cells[state.cursor];

  for (let i = 0; i < CELLS; i++) {
    const { cell, value, notes } = cellEls[i];
    const r = Math.floor(i / SIZE), c = i % SIZE;
    const isCursor = i === state.cursor;
    const sameBox =
      Math.floor(r / 3) === Math.floor(cursorRow / 3) &&
      Math.floor(c / 3) === Math.floor(cursorCol / 3);

    cell.classList.toggle("is-cursor", isCursor);
    // Tinted so the eye can follow what the selected cell constrains.
    cell.classList.toggle("is-peer", !isCursor && (r === cursorRow || c === cursorCol || sameBox));
    cell.classList.toggle(
      "is-match",
      !isCursor && !!cursorValue && state.cells[i] === cursorValue
    );
    cell.classList.toggle("is-clash", clashes(i));
    cell.classList.toggle("is-revealed", !!state.revealed[i]);

    const digits = state.notes[i] || "";
    value.textContent = state.cells[i] || "";
    notes.hidden = !!state.cells[i] || !digits;
    if (!notes.hidden) {
      for (let d = 1; d <= SIZE; d++) {
        notes.children[d - 1].textContent = digits.includes(String(d)) ? d : "";
      }
    }
  }

  document.getElementById("sd-mistakes").textContent = state.mistakes;

  const notesBtn = document.getElementById("sd-notes-btn");
  notesBtn.classList.toggle("is-on", state.notesMode);
  notesBtn.setAttribute("aria-pressed", state.notesMode ? "true" : "false");
  document.getElementById("sd-undo-btn").disabled = undoStack.length === 0;

  // Each key shows how many of that digit are left, and greys out at 0.
  document.querySelectorAll(".sd-key").forEach((key) => {
    const left = SIZE - placed(key.dataset.digit);
    key.classList.toggle("is-done", left <= 0);
    key.querySelector(".sd-key__left").textContent = left > 0 ? left : "";
  });

  const message = document.getElementById("sd-message");
  if (state.completed) {
    message.hidden = false;
    message.className = "sd-message is-success";
    message.textContent =
      state.mistakes === 0
        ? "Solved, with no mistakes. Nicely done."
        : `Solved, with ${state.mistakes} mistake${state.mistakes === 1 ? "" : "s"}.`;
  } else if (state.mistakes >= MAX_MISTAKES) {
    message.hidden = false;
    message.className = "sd-message is-error";
    message.textContent = `That's ${MAX_MISTAKES} mistakes. Keep going, or restart.`;
  } else {
    message.hidden = true;
  }
}

// --- Playing ---------------------------------------------------------------

function select(i) {
  state.cursor = i;
  paint();
  saveState();
}

function enter(digit) {
  const i = state.cursor;
  if (given[i] || state.completed) return;
  snapshot();

  if (state.notesMode) {
    const current = state.notes[i] || "";
    const next = current.includes(digit)
      ? [...current].filter((d) => d !== digit).join("")
      : [...current + digit].sort().join("");
    if (next) state.notes[i] = next;
    else delete state.notes[i];
    state.cells[i] = "";
  } else if (state.cells[i] === digit) {
    state.cells[i] = "";
  } else {
    state.cells[i] = digit;
    delete state.notes[i];
    // Committing a digit rules it out nearby, so those marks come off.
    for (const j of PEERS[i]) {
      const marks = state.notes[j];
      if (!marks || !marks.includes(digit)) continue;
      const left = [...marks].filter((d) => d !== digit).join("");
      if (left) state.notes[j] = left;
      else delete state.notes[j];
    }
    // A digit contradicting the solution is a mistake, counted once per
    // entry. With no stored solution, only clashes give feedback.
    if (SD.solution && SD.solution[i] !== digit) state.mistakes++;
  }

  state.completed = isSolved();
  paint();
  saveState();
}

function erase() {
  const i = state.cursor;
  if (given[i] || state.completed) return;
  if (!state.cells[i] && !state.notes[i]) return;
  snapshot();
  state.cells[i] = "";
  delete state.notes[i];
  paint();
  saveState();
}

// Fills the selected cell -- or the next one still wrong or empty -- from
// the solution, marked so it's clear it wasn't solved.
function hint() {
  if (!SD.solution || state.completed) return;
  let i = state.cursor;
  if (given[i] || state.cells[i] === SD.solution[i]) {
    i = state.cells.findIndex((v, n) => !given[n] && v !== SD.solution[n]);
    if (i === -1) return;
  }
  snapshot();
  state.cursor = i;
  state.cells[i] = SD.solution[i];
  state.revealed[i] = true;
  delete state.notes[i];
  state.completed = isSolved();
  paint();
  saveState();
}

function move(dr, dc) {
  const r = Math.floor(state.cursor / SIZE), c = state.cursor % SIZE;
  select(((r + dr + SIZE) % SIZE) * SIZE + ((c + dc + SIZE) % SIZE));
}

function toggleNotes() {
  state.notesMode = !state.notesMode;
  paint();
  saveState();
}

function restart() {
  if (!confirm("Clear the grid and start this puzzle again?")) return;
  snapshot();
  SD.puzzle.split("").forEach((ch, i) => {
    state.cells[i] = ch === "0" ? "" : ch;
  });
  state.notes = {};
  state.revealed = {};
  state.mistakes = 0;
  state.completed = false;
  paint();
  saveState();
}

const ARROWS = {
  ArrowUp: [-1, 0],
  ArrowDown: [1, 0],
  ArrowLeft: [0, -1],
  ArrowRight: [0, 1],
};

document.addEventListener("keydown", (e) => {
  if (e.target.tagName === "INPUT" || e.target.tagName === "TEXTAREA") return;
  if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "z") {
    undo();
    e.preventDefault();
    return;
  }
  if (e.metaKey || e.ctrlKey || e.altKey) return;

  const key = e.key;
  let handled = true;
  if (/^[1-9]$/.test(key)) enter(key);
  else if (key === "Backspace" || key === "Delete" || key === "0") erase();
  else if (ARROWS[key]) move(...ARROWS[key]);
  else if (key === "n" || key === "N") toggleNotes();
  else if (key === "h" || key === "H") hint();
  else handled = false;

  if (handled) e.preventDefault();
});

document.querySelectorAll(".sd-key").forEach((key) => {
  key.addEventListener("click", () => enter(key.dataset.digit));
});
document.getElementById("sd-erase-btn").addEventListener("click", erase);
document.getElementById("sd-notes-btn").addEventListener("click", toggleNotes);
document.getElementById("sd-undo-btn").addEventListener("click", undo);
document.getElementById("sd-restart-btn").addEventListener("click", restart);
const hintBtn = document.getElementById("sd-hint-btn");
if (hintBtn) hintBtn.addEventListener("click", hint);

loadState();
buildBoard();
paint();
