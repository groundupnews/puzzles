"use strict";

const GP = window.GROUPUP;
const S = GP.scoring;
const GROUP_SIZE = 4;
const GROUP_COUNT = Math.floor(GP.words.length / GROUP_SIZE);
const $ = (id) => document.getElementById(id);

const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
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
const CONFETTI = ["#9b3d8f", "#00B1F0", "#F7C600", "#1f8a5b", "#d4582f", "#4d57c4"];

const STORAGE_KEY = `groupup-${GP.pk}`;

const state = {
  order: GP.words.slice(),
  found: [],
  selected: [],
  mistakes: 0,
  tried: [],
  seconds: 0,
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

const isSolved = () => state.found.length === GROUP_COUNT;
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

// --- Sound ---
// Synthesised with the Web Audio API rather than played from files: none
// of the other games has a "wrong answer" sound to borrow, and this keeps
// the set matched. Browsers only allow audio after a click, so the
// context is created on Start (or on the sound button).
const SOUND_KEY = "groupup-sound";
let soundOn = true;
try {
  soundOn = localStorage.getItem(SOUND_KEY) !== "off";
} catch (_) {}
let audio = null;

function unlockAudio() {
  const Context = window.AudioContext || window.webkitAudioContext;
  if (!audio && Context) audio = new Context();
  if (audio && audio.state === "suspended") audio.resume();
}

// notes: [[frequency in Hz, start in s, length in s], ...]
function play(notes, wave = "triangle", volume = 0.15) {
  if (!soundOn || !audio) return;
  const now = audio.currentTime;
  notes.forEach(([frequency, start, length]) => {
    const osc = audio.createOscillator();
    const gain = audio.createGain();
    osc.type = wave;
    osc.frequency.value = frequency;
    gain.gain.setValueAtTime(volume, now + start);
    gain.gain.exponentialRampToValueAtTime(0.001, now + start + length);
    osc.connect(gain).connect(audio.destination);
    osc.start(now + start);
    osc.stop(now + start + length);
  });
}

const SOUNDS = {
  tap: () => play([[880, 0, 0.05]], "sine", 0.08),
  shuffle: () => play([[660, 0, 0.04], [740, 0.05, 0.04], [830, 0.1, 0.04]], "sine", 0.06),
  start: () => play([[392, 0, 0.12], [523, 0.1, 0.12], [784, 0.2, 0.3]]),
  correct: () => play([[523, 0, 0.14], [659, 0.09, 0.14], [784, 0.18, 0.14], [1047, 0.27, 0.4]]),
  oneAway: () => play([[440, 0, 0.12], [415, 0.12, 0.3]], "square", 0.05),
  wrong: () => play([[220, 0, 0.18], [165, 0.15, 0.35]], "sawtooth", 0.06),
  win: () =>
    play([[523, 0, 0.18], [659, 0.15, 0.18], [784, 0.3, 0.18], [1047, 0.45, 0.18], [784, 0.63, 0.14], [1047, 0.77, 0.8]]),
};

function renderSoundButton() {
  const button = $("gp-sound-btn");
  button.setAttribute("aria-pressed", soundOn);
  button.querySelector("i").className = `fa-solid ${soundOn ? "fa-volume-high" : "fa-volume-xmark"}`;
}

function startClock() {
  if (timer || isSolved()) return;
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
    card.innerHTML = SHAPES[i];
    const body = el("div", "gp-group__body");
    body.append(
      el("div", "gp-group__order", `Found ${ORDINALS[i]}`),
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
}

function renderStatus() {
  const solved = isSolved();
  $("gp-points").textContent = `${solved ? points() + bonus() : points()} pts`;
  $("gp-clock").textContent = clock(state.seconds);
  $("gp-mistakes").textContent = state.mistakes;
  const left = secondsLeft();
  const grace = S.grace_seconds - state.seconds;
  $("gp-bonus").hidden = solved;
  $("gp-bonus").classList.toggle("is-low", left > 0 && left <= 10);
  $("gp-bonus-fill").style.width = `${(100 * left) / (S.bonus_seconds - S.grace_seconds)}%`;
  $("gp-bonus-label").textContent = !left
    ? "Bonus gone. Keep going!"
    : grace > 0
      ? `+${bonus()} bonus, full for ${grace}s`
      : `+${bonus()} time bonus`;
}

function renderResult(celebrate) {
  $("gp-result").hidden = !isSolved();
  if (!isSolved()) return;
  const n = state.mistakes;
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
  const solved = isSolved();
  $("gp-board").hidden = solved;
  $("gp-controls").hidden = solved;
  $("gp-rules-btn").hidden = solved || $("gp-game").hidden;
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

function confetti() {
  if (reducedMotion) return;
  const layer = el("div", "gp-confetti");
  for (let i = 0; i < 90; i++) {
    const bit = el("span", "");
    bit.style.left = `${Math.random() * 100}%`;
    bit.style.background = CONFETTI[i % CONFETTI.length];
    bit.style.animationDelay = `${Math.random() * 0.7}s`;
    bit.style.animationDuration = `${2 + Math.random() * 1.5}s`;
    bit.style.setProperty("--drift", `${Math.random() * 240 - 120}px`);
    bit.style.setProperty("--spin", `${Math.random() * 1080 - 540}deg`);
    layer.appendChild(bit);
  }
  document.body.appendChild(layer);
  setTimeout(() => layer.remove(), 4500);
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
  SOUNDS.tap();
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
      setTimeout(SOUNDS.win, 450);
      confetti();
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

function shuffle(array) {
  for (let i = array.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [array[i], array[j]] = [array[j], array[i]];
  }
}

function showSplash() {
  stopClock();
  const begun = state.seconds > 0 || state.found.length > 0 || state.mistakes > 0;
  $("gp-start").textContent = begun ? "Continue" : "Start";
  $("gp-splash").hidden = false;
  $("gp-game").hidden = true;
  render();
}

function showGame(options) {
  $("gp-splash").hidden = true;
  $("gp-game").hidden = false;
  startClock();
  render(options);
}

$("gp-start").addEventListener("click", () => {
  unlockAudio();
  SOUNDS.start();
  showGame({ deal: true });
  window.scrollTo({ top: 0 });
});
$("gp-rules-btn").addEventListener("click", showSplash);
$("gp-sound-btn").addEventListener("click", () => {
  soundOn = !soundOn;
  try {
    localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off");
  } catch (_) {}
  unlockAudio();
  renderSoundButton();
  SOUNDS.tap();
});
$("gp-submit").addEventListener("click", submit);
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
renderSoundButton();
if (isSolved()) showGame();
else showSplash();
