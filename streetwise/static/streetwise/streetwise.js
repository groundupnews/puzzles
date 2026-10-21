"use strict";

// The server keeps the guesses and grades them; this page only draws what
// it sends back. See streetwise/views.py.
const SW = window.STREETWISE;
const $ = (id) => document.getElementById(id);

const MARKS = { wrong: "🟥", close: "🟨", right: "🟩" };
const VERDICTS = {
  wrong: () => "Wrong party",
  close: (g) => `Right party. Go ${g.direction}`,
  right: () => "Got it",
};

let state = SW.state;
let busy = false;

const picked = () => document.querySelector('input[name="party"]:checked');
const percent = () => Number($("sw-percent").value);

function el(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

// A party's name on its colour, as Django's slugify names the classes in
// streetwise.css.
function chip(party) {
  return el("span", `sw-chip sw-p-${party.toLowerCase().replace(/\s+/g, "-")}`, party);
}

function renderPick() {
  const party = picked();
  $("sw-percent-out").textContent = `${party ? `${party.value} — ` : ""}${percent()}%`;
  $("sw-submit").disabled = busy || !party;
}

function render() {
  const { guesses, hints, attempts, finished, won } = state;

  $("sw-guesses").replaceChildren(
    ...guesses.map((g) => {
      const row = el("li", `sw-guess is-${g.grade}`);
      const pick = el("span", "sw-guess__pick");
      pick.append(chip(g.party), ` ${g.percent}%`);
      row.append(
        el("span", "sw-guess__mark", MARKS[g.grade]),
        pick,
        el("span", "sw-guess__verdict", VERDICTS[g.grade](g))
      );
      row.firstChild.setAttribute("aria-hidden", "true");
      return row;
    })
  );

  $("sw-hints").replaceChildren(
    ...hints.flatMap((h) => [el("dt", "", h.label), el("dd", "", h.text)])
  );

  const left = attempts - guesses.length;
  $("sw-left").textContent = `${left} guess${left === 1 ? "" : "es"} left`;
  $("sw-form").hidden = finished;
  $("sw-result").hidden = !finished;
  if (finished) {
    $("sw-result-title").textContent = won
      ? `You got it in ${guesses.length}!`
      : "Out of guesses";
    $("sw-result-body").innerHTML = state.result;
    GU.news();
  }
  renderPick();
}

async function submit(event) {
  event.preventDefault();
  const party = picked();
  if (busy || !party) return;
  busy = true;
  renderPick();
  try {
    const resp = await fetch(SW.guessUrl, {
      method: "POST",
      headers: { "Content-Type": "application/json", "X-CSRFToken": SW.csrfToken },
      body: JSON.stringify({ party: party.value, percent: percent() }),
    });
    const data = await resp.json();
    if (!resp.ok) {
      $("sw-message").textContent = data.error;
      return;
    }
    state = data;
    const last = state.guesses[state.guesses.length - 1];
    $("sw-message").textContent = state.finished ? "" : VERDICTS[last.grade](last) + ".";
    if (state.won) GU.win();
    render();
    if (state.finished) $("sw-result").scrollIntoView({ behavior: GU.reducedMotion ? "auto" : "smooth" });
  } catch (_) {
    $("sw-message").textContent = "Couldn't check that guess. Try again.";
  } finally {
    busy = false;
    renderPick();
  }
}

function shareText() {
  const { guesses, won, attempts } = state;
  return [
    `Streetwise${SW.number ? ` #${SW.number}` : ""} 🇿🇦`,
    guesses.map((g) => MARKS[g.grade]).join(""),
    `${won ? guesses.length : "X"}/${attempts}`,
    location.origin + location.pathname,
  ].join("\n");
}

document.querySelectorAll('input[name="party"]').forEach((input) => {
  input.addEventListener("change", () => {
    GU.sounds.tap();
    renderPick();
  });
});
$("sw-percent").addEventListener("input", renderPick);
$("sw-form").addEventListener("submit", submit);
$("sw-share").addEventListener("click", () => GU.share($("sw-share"), shareText()));

// The game loads under the splash (see streetwise.css), out of reach of
// the keyboard and screen readers until Start.
const game = document.querySelector(".sw-game");
const splash = GU.splash({
  begun: () => state.guesses.length > 0,
  onStart: () => (game.inert = false),
  onPause: () => (game.inert = true),
});
render();
if (state.finished) splash.skip();
else splash.show();
