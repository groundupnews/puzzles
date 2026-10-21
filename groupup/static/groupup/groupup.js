"use strict";

const GP = window.GROUPUP;
const S = GP.scoring;
const GROUP_SIZE = 4;
const GROUP_COUNT = Math.floor(GP.words.length / GROUP_SIZE);
const $ = (id) => document.getElementById(id);

const reducedMotion = GU.reducedMotion;
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, reducedMotion ? 0 : ms));

const SHAPES = [
  '<circle cx="12" cy="12" r="9"/>',
  '<rect x="4" y="4" width="16" height="16"/>',
  '<polygon points="12 3 22 20 2 20"/>',
  '<polygon points="12 2 22 12 12 22 2 12"/>',
].map(
  (shape) =>
    `<svg class="gp-group__shape" width="28" height="28" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">${shape}</svg>`
);
const ORDINALS = ["1st", "2nd", "3rd", "4th"];
const PRAISE = ["Nice one!", "Well spotted!", "Got it!", "Sharp!"];
const KEYCAPS = ["1\uFE0F\u20E3", "2\uFE0F\u20E3", "3\uFE0F\u20E3", "4\uFE0F\u20E3"];

const STORAGE_KEY = `groupup-${GP.pk}`;

const state = {
  order: GP.words.slice(),
  found: [],
  selected: [],
  mistakes: 0,
  tried: [],
  guesses: [],
  seconds: 0,
  // Given up: the groups the player didn't find were added to `found`
  // with revealed: true, so the whole answer is on show.
  gaveUp: false,
};

let busy = false;
let timer = null;

const sameWords = (a, b) => a.slice().sort().join("\n") === b.slice().sort().join("\n");

function loadState() {
  let saved;
  try {
    saved = JSON.parse(localStorage.getItem(STORAGE_KEY));
  } catch (_) {
    return;
  }
  if (!saved || !Array.isArray(saved.order) || !sameWords(saved.order, GP.words)) return;
  Object.assign(state, saved);
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (_) {
  }
}

const isSolved = () => state.found.length === GROUP_COUNT && !state.gaveUp;
const isOver = () => state.found.length === GROUP_COUNT;
const foundByPlayer = () => state.found.filter((group) => !group.revealed).length;
const points = () => Math.max(0, S.start - S.mistake * state.mistakes);
const secondsLeft = () => Math.max(0, S.bonus_seconds - Math.max(state.seconds, S.grace_seconds));
const bonus = () => secondsLeft() * S.bonus_per_second;
const clock = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;

function el(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function say(text) {
  $("gp-message").textContent = text;
}

// The sounds only GroupUp makes; the shared ones are in gu/game.js.
const SOUNDS = {
  shuffle: () => GU.play([[660, 0, 0.04], [740, 0.05, 0.04], [830, 0.1, 0.04]], "sine", 0.06),
  correct: () => GU.play([[523, 0, 0.14], [659, 0.09, 0.14], [784, 0.18, 0.14], [1047, 0.27, 0.4]]),
  oneAway: () => GU.play([[440, 0, 0.12], [415, 0.12, 0.3]], "square", 0.05),
  wrong: () => GU.play([[220, 0, 0.18], [165, 0.15, 0.35]], "sawtooth", 0.06),
  // A sad trombone, three steps down and a long last note.
  giveUp: () =>
    GU.play([[392, 0, 0.32], [370, 0.32, 0.32], [349, 0.64, 0.32], [330, 0.96, 0.9]], "triangle", 0.14),
};

function startClock() {
  if (timer || isOver()) return;
  timer = setInterval(() => {
    state.seconds++;
    saveState();
    renderStatus();
  }, 1000);
}

function stopClock() {
  clearInterval(timer);
  timer = null;
}

function renderFound(animateNewest) {
  const container = $("gp-found");
  container.innerHTML = "";
  state.found.forEach((group, i) => {
    const card = el("section", "gp-group");
    if (animateNewest && i === state.found.length - 1) card.classList.add("is-new");
    if (group.revealed) card.classList.add("is-revealed");
    card.innerHTML = SHAPES[i];
    const body = el("div", "gp-group__body");
    body.append(
      el("div", "gp-group__order", group.revealed ? "Not found" : `Found ${ORDINALS[i]}`),
      el("h2", "gp-group__label", group.label),
      el("p", "gp-group__words", group.words.join(", "))
    );
    card.appendChild(body);
    container.appendChild(card);
  });
}

function renderBoard(deal) {
  const board = $("gp-board");
  board.innerHTML = "";
  const done = new Set(state.found.flatMap((group) => group.words));
  state.order
    .filter((word) => !done.has(word))
    .forEach((word, i) => {
      const tile = el("button", "gp-tile", word);
      tile.type = "button";
      tile.setAttribute("aria-pressed", state.selected.includes(word));
      if (deal) {
        tile.classList.add("is-dealt");
        tile.style.setProperty("--i", i);
      }
      tile.addEventListener("click", () => toggle(word, tile));
      board.appendChild(tile);
    });
}

function renderButtons() {
  $("gp-submit").disabled = busy || state.selected.length !== GROUP_SIZE;
  $("gp-deselect").disabled = busy || state.selected.length === 0;
  $("gp-shuffle").disabled = busy;
  $("gp-give-up").disabled = busy;
}

function renderStatus() {
  const solved = isSolved();
  $("gp-points").textContent = state.gaveUp ? "Gave up" : `${solved ? points() + bonus() : points()} pts`;
  $("gp-clock").textContent = clock(state.seconds);
  $("gp-mistakes").textContent = state.mistakes;
  const left = secondsLeft();
  const grace = S.grace_seconds - state.seconds;
  $("gp-bonus").hidden = isOver();
  $("gp-bonus").classList.toggle("is-low", left > 0 && left <= 10);
  $("gp-bonus-fill").style.width = `${(100 * left) / (S.bonus_seconds - S.grace_seconds)}%`;
  $("gp-bonus-label").textContent = !left
    ? "Bonus gone. Keep going!"
    : grace > 0
      ? `+${bonus()} bonus, full for ${grace}s`
      : `+${bonus()} time bonus`;
}

function renderResult(celebrate) {
  $("gp-result").hidden = !isOver();
  if (!isOver()) return;
  GU.news();
  const n = state.mistakes;
  $("gp-result").classList.toggle("is-gave-up", state.gaveUp);
  if (state.gaveUp) {
    const found = foundByPlayer();
    $("gp-result-eyebrow").textContent = "Answers revealed";
    $("gp-result-score").textContent = `${found} of ${GROUP_COUNT}`;
    $("gp-result-unit").textContent = "found";
    $("gp-result-detail").textContent =
      `You found ${found} group${found === 1 ? "" : "s"} with ${n} mistake${n === 1 ? "" : "s"}. ` +
      "The rest are below.";
    return;
  }
  $("gp-result-detail").textContent =
    `${clock(state.seconds)} with ${n} mistake${n === 1 ? "" : "s"}: ${points()} points` +
    (bonus() ? ` + ${bonus()} time bonus.` : ".");
  const total = points() + bonus();
  if (celebrate) countUp($("gp-result-score"), total);
  else $("gp-result-score").textContent = total;
}

function render({ deal = false, newGroup = false, celebrate = false } = {}) {
  renderFound(newGroup);
  renderBoard(deal);
  renderStatus();
  renderResult(celebrate);
  renderButtons();
  const over = isOver();
  $("gp-board").hidden = over;
  $("gp-controls").hidden = over;
  $("gu-rules-btn").hidden = over;
}

function countUp(node, target) {
  const begin = performance.now();
  const duration = reducedMotion ? 0 : 1200;
  const step = (now) => {
    const t = duration ? Math.min(1, (now - begin) / duration) : 1;
    node.textContent = Math.round(target * (1 - Math.pow(1 - t, 3)));
    if (t < 1) requestAnimationFrame(step);
  };
  requestAnimationFrame(step);
}

function floatPenalty() {
  if (reducedMotion) return;
  const tag = el("span", "gp-penalty", `−${S.mistake}`);
  $("gp-points").parentNode.appendChild(tag);
  tag.addEventListener("animationend", () => tag.remove());
}

function toggle(word, tile) {
  if (busy) return;
  if (state.selected.includes(word)) {
    state.selected = state.selected.filter((w) => w !== word);
  } else if (state.selected.length < GROUP_SIZE) {
    state.selected.push(word);
  } else {
    return;
  }
  GU.sounds.tap();
  tile.setAttribute("aria-pressed", state.selected.includes(word));
  say("");
  saveState();
  renderButtons();
}

async function check(guess) {
  const resp = await fetch(GP.checkUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": GP.csrfToken },
    body: JSON.stringify({ words: guess }),
  });
  if (!resp.ok) throw new Error(resp.status);
  return resp.json();
}

async function submit() {
  const guess = state.selected.slice();
  if (state.tried.some((tried) => sameWords(tried, guess))) {
    say("You've already tried that one.");
    return;
  }
  busy = true;
  renderButtons();
  const tiles = [...document.querySelectorAll('.gp-tile[aria-pressed="true"]')];
  tiles.forEach((tile, i) => {
    tile.style.setProperty("--i", i);
    tile.classList.add("is-hop");
  });

  let result;
  try {
    [result] = await Promise.all([check(guess), wait(500)]);
  } catch (_) {
    busy = false;
    render();
    say("Couldn't check that guess. Try again.");
    return;
  }
  tiles.forEach((tile) => tile.classList.remove("is-hop"));
  state.guesses.push(guess);

  if (result.correct) {
    SOUNDS.correct();
    tiles.forEach((tile) => tile.classList.add("is-found"));
    await wait(300);
    state.found.push({ label: result.label, words: result.words });
    state.selected = [];
    busy = false;
    saveState();
    if (isSolved()) {
      stopClock();
      say("");
      render({ newGroup: true, celebrate: true });
      setTimeout(GU.sounds.win, 450);
      GU.confetti();
      window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
    } else {
      say(PRAISE[(state.found.length - 1) % PRAISE.length]);
      render({ newGroup: true });
    }
  } else {
    (result.one_away ? SOUNDS.oneAway : SOUNDS.wrong)();
    tiles.forEach((tile) => tile.classList.add("is-shake"));
    state.mistakes++;
    state.tried.push(guess);
    saveState();
    renderStatus();
    floatPenalty();
    say(`${result.one_away ? "One away!" : "Not a group."} That's ${S.mistake} points off.`);
    await wait(450);
    tiles.forEach((tile) => tile.classList.remove("is-shake"));
    busy = false;
    renderButtons();
  }
}

// Asks for every group and shows the ones not yet found, which ends the
// game. Confirmed first: there's no taking it back.
async function giveUp() {
  if (!confirm("Give up and see all the groups?")) return;
  let groups;
  try {
    const resp = await fetch(GP.revealUrl, {
      method: "POST",
      headers: { "X-CSRFToken": GP.csrfToken },
    });
    if (!resp.ok) throw new Error(resp.status);
    groups = (await resp.json()).groups;
  } catch (_) {
    say("Couldn't get the answers. Try again.");
    return;
  }
  groups
    .filter((group) => !state.found.some((found) => sameWords(found.words, group.words)))
    .forEach((group) => state.found.push({ label: group.label, words: group.words, revealed: true }));
  state.gaveUp = true;
  state.selected = [];
  stopClock();
  SOUNDS.giveUp();
  say("");
  saveState();
  render();
  window.scrollTo({ top: 0, behavior: reducedMotion ? "auto" : "smooth" });
}

function shareText() {
  const found = {};
  state.found.forEach((group, i) => group.words.forEach((word) => (found[word] = KEYCAPS[i])));
  const n = state.mistakes;
  const summary = state.gaveUp
    ? `Found ${foundByPlayer()} of ${GROUP_COUNT} groups, ${n} mistake${n === 1 ? "" : "s"}, then gave up`
    : `${points() + bonus()} points in ${clock(state.seconds)}, ${n} mistake${n === 1 ? "" : "s"}`;
  return [
    GP.name,
    summary,
    ...state.guesses.map((guess) => guess.map((word) => found[word]).join("")),
    location.origin + location.pathname,
  ].join("\n");
}

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

const splash = GU.splash({
  begun: () => state.seconds > 0 || state.found.length > 0 || state.mistakes > 0,
  onStart: () => {
    startClock();
    render({ deal: true });
  },
  onPause: () => {
    stopClock();
    render();
  },
});

$("gp-submit").addEventListener("click", submit);
$("gp-give-up").addEventListener("click", giveUp);
$("gp-share").addEventListener("click", () => GU.share($("gp-share"), shareText()));
$("gp-deselect").addEventListener("click", () => {
  state.selected = [];
  document.querySelectorAll(".gp-tile").forEach((tile) => tile.setAttribute("aria-pressed", "false"));
  say("");
  saveState();
  renderButtons();
});
$("gp-shuffle").addEventListener("click", () => {
  shuffle(state.order);
  SOUNDS.shuffle();
  saveState();
  render({ deal: true });
});

loadState();
if (isOver()) splash.skip();
else splash.show();
