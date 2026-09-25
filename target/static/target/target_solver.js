"use strict";

// Rules carried over from the Target on the main GroundUp site: words of
// four letters or more, every one containing the centre letter, each grid
// letter usable only as often as it appears, and scoring tiers at three
// quarters and nine tenths of the answer list.
//
// A guess is checked by hashing it and looking for that hash among the
// ones the page was given, so the answers are never in the page. The site
// shipped its own SHA-256; crypto.subtle does the same job, and needs a
// secure context (https or localhost).

const TG = window.TARGET;
const STORAGE_KEY = `target-solver-${TG.pk}`;
const HASHES = new Set(TG.hashedWords);

const state = {
  found: [], // in the order they were found
  revealed: [], // the ones a hint gave away, kept apart so they're marked
  entry: "",
  order: TG.letters.split(""), // shuffling only ever reorders the outer ring
};

function loadState() {
  try {
    const saved = JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    if (!saved) return;
    if (Array.isArray(saved.found)) state.found = saved.found;
    if (Array.isArray(saved.revealed)) state.revealed = saved.revealed;
    if (Array.isArray(saved.order) && saved.order.length === TG.letters.length) {
      state.order = saved.order;
    }
  } catch (_) {
    // Corrupt or unavailable storage: start fresh rather than fail.
  }
}

function saveState() {
  try {
    localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({
        found: state.found,
        revealed: state.revealed,
        order: state.order,
      })
    );
  } catch (_) {
    // Storage unavailable -- play still works, it just won't be restored.
  }
}

async function hash(word) {
  const bytes = new TextEncoder().encode(word);
  const digest = await crypto.subtle.digest("SHA-256", bytes);
  return [...new Uint8Array(digest)]
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

// The grid needs enough of each letter, and the centre letter must be
// in the word.
function spellable(word) {
  if (!word.includes(TG.centre)) return false;
  const pool = TG.letters.split("");
  for (const char of word) {
    const at = pool.indexOf(char);
    if (at === -1) return false;
    pool.splice(at, 1);
  }
  return true;
}

function tier(count) {
  if (count >= TG.total) return "Perfect";
  if (count >= TG.veryGood) return "Very good";
  if (count >= TG.good) return "Good";
  return "";
}

function nextTier(count) {
  if (count < TG.good) return { name: "Good", at: TG.good };
  if (count < TG.veryGood) return { name: "Very good", at: TG.veryGood };
  if (count < TG.total) return { name: "Perfect", at: TG.total };
  return null;
}

// --- Rendering -------------------------------------------------------------

function renderGrid() {
  const grid = document.getElementById("tg-grid");
  grid.innerHTML = "";
  // The centre letter holds the middle cell; the other eight fill in
  // around it in whatever order the shuffle left them.
  const outer = state.order.filter((_, i) => i !== 0);
  const cells = [...outer.slice(0, 4), state.order[0], ...outer.slice(4)];
  cells.forEach((letter) => {
    const cell = document.createElement("button");
    cell.type = "button";
    cell.className = "tg-cell";
    if (letter === state.order[0]) cell.classList.add("is-centre");
    cell.textContent = letter.toUpperCase();
    cell.addEventListener("click", () => {
      state.entry += letter;
      renderEntry();
    });
    grid.appendChild(cell);
  });
}

function renderEntry() {
  const input = document.getElementById("tg-entry");
  input.value = state.entry.toUpperCase();
}

function renderScore() {
  const count = state.found.length;
  const label = tier(count);
  const next = nextTier(count);

  document.getElementById("tg-count").textContent = count;
  document.getElementById("tg-status").textContent = `Found ${count}/${TG.total}`;

  const badge = document.getElementById("tg-tier");
  badge.hidden = !label;
  badge.textContent = label;

  const toGo = document.getElementById("tg-to-go");
  toGo.textContent = next
    ? `${next.at - count} to "${next.name}"`
    : "Every word found.";

  document.getElementById("tg-bar-fill").style.width =
    `${TG.total ? Math.min(100, (count / TG.total) * 100) : 0}%`;
}

function renderFound() {
  const list = document.getElementById("tg-found");
  list.innerHTML = "";
  // Longest first, so the nine-letter word rises to the top once found.
  [...state.found]
    .sort((a, b) => b.length - a.length || a.localeCompare(b))
    .forEach((word) => {
      const item = document.createElement("span");
      item.className = "tg-word";
      if (word.length === 9) item.classList.add("is-nine");
      if (state.revealed.includes(word)) {
        item.classList.add("is-revealed");
        item.title = "Given by a hint";
      }
      item.textContent = word.toUpperCase();
      list.appendChild(item);
    });
  document.getElementById("tg-found-empty").hidden = state.found.length > 0;
}

function render() {
  renderGrid();
  renderEntry();
  renderScore();
  renderFound();
}

function say(text, kind) {
  const message = document.getElementById("tg-message");
  message.hidden = !text;
  message.className = `tg-message${kind ? " is-" + kind : ""}`;
  message.textContent = text;
}

// --- Playing ---------------------------------------------------------------

async function submit() {
  const word = state.entry.toLowerCase();
  state.entry = "";
  renderEntry();

  if (!word) return;
  if (word.length < 4) return say("Words must be at least four letters.", "error");
  if (!word.includes(TG.centre)) {
    return say(`Every word must use the centre letter, ${TG.centre.toUpperCase()}.`, "error");
  }
  if (!spellable(word)) return say("That word doesn't fit the grid letters.", "error");
  if (state.found.includes(word)) return say(`You already have ${word.toUpperCase()}.`, null);

  if (!HASHES.has(await hash(word))) {
    return say(`${word.toUpperCase()} isn't in our dictionary.`, "error");
  }

  state.found.push(word);
  saveState();
  render();
  say(
    word.length === 9
      ? `${word.toUpperCase()} \u2014 that's the nine-letter word!`
      : `${word.toUpperCase()} is good.`,
    "success"
  );
}

document.getElementById("tg-form").addEventListener("submit", (e) => {
  e.preventDefault();
  submit();
});

document.getElementById("tg-entry").addEventListener("input", (e) => {
  // Only grid letters, so the box can't hold something unspellable.
  state.entry = e.target.value
    .toLowerCase()
    .split("")
    .filter((ch) => TG.letters.includes(ch))
    .join("");
  renderEntry();
});

document.getElementById("tg-shuffle-btn").addEventListener("click", () => {
  const outer = state.order.slice(1);
  for (let i = outer.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [outer[i], outer[j]] = [outer[j], outer[i]];
  }
  state.order = [state.order[0], ...outer];
  saveState();
  renderGrid();
});

// The page holds only hashes, so it can't pick a word to reveal: it sends
// what's been found and the server names one that's missing.
document.getElementById("tg-hint-btn").addEventListener("click", async () => {
  const button = document.getElementById("tg-hint-btn");
  button.disabled = true;
  try {
    const response = await fetch(TG.hintUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": TG.csrfToken },
      body: JSON.stringify({ found: state.found }),
    });
    if (!response.ok) return say("Couldn't fetch a hint just now.", "error");
    const { word } = await response.json();
    if (!word) return say("You've found every word.", "success");
    state.found.push(word);
    state.revealed.push(word);
    saveState();
    render();
    say(`Here's one: ${word.toUpperCase()}.`, null);
  } catch (_) {
    say("Couldn't fetch a hint just now.", "error");
  } finally {
    button.disabled = false;
  }
});

document.getElementById("tg-clear-btn").addEventListener("click", () => {
  state.entry = "";
  renderEntry();
  say("", null);
});

loadState();
render();

// The solution is on the page only once the puzzle is old enough for the
// server to have sent it (Target.is_solution_public).
const solutionToggle = document.getElementById("tg-solution-toggle");
if (solutionToggle) {
  solutionToggle.addEventListener("click", () => {
    const words = document.getElementById("tg-solution-words");
    words.hidden = !words.hidden;
    solutionToggle.textContent = words.hidden ? "Show solution" : "Hide solution";
    solutionToggle.setAttribute("aria-expanded", String(!words.hidden));
  });
}
