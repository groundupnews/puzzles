"use strict";

const QZ = window.QUIZ;
const LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ";

// Progress is saved to localStorage per quiz, same rationale as the
// crossword solver: reloading or returning later restores exactly where
// the solver left off, including a completed result.
const STORAGE_KEY = `quiz-solver-${QZ.pk}`;

const state = {
  selected: {}, // question id -> selected answer id
  index: 0, // which question is on screen while taking the quiz
  results: null, // {results: [...], score, total} once submitted
};

function loadState() {
  let saved;
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return;
    saved = JSON.parse(raw);
  } catch (_) {
    return;
  }
  if (!saved) return;
  state.selected = saved.selected || {};
  state.index = saved.index || 0;
  state.results = saved.results || null;
}

function saveState() {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  } catch (_) {
    // Storage unavailable (private browsing, quota, etc.) -- taking the
    // quiz still works, it just won't be restored next time.
  }
}

function resultFor(questionId) {
  if (!state.results) return null;
  return state.results.results.find((r) => r.question_id === questionId) || null;
}

const CHECK_SVG =
  '<svg class="qz-option__tick" width="20" height="20" viewBox="0 0 24 24" fill="none" ' +
  'stroke="currentColor" stroke-width="3" stroke-linecap="round" stroke-linejoin="round" ' +
  'aria-hidden="true"><polyline points="20 6 9 17 4 12"/></svg>';

// One answer row. `mode` is "" while taking the quiz, or "correct"/"wrong"
// once the quiz has been marked, which is what colours the row.
function optionEl(question, answer, letter, selected, mode, interactive) {
  const el = document.createElement(interactive ? "button" : "div");
  el.className = "qz-option";
  if (selected) el.classList.add("is-selected");
  if (mode) el.classList.add(`is-${mode}`);
  if (interactive) el.type = "button";

  const tag = document.createElement("span");
  tag.className = "qz-option__letter";
  tag.textContent = letter;

  const text = document.createElement("span");
  text.className = "qz-option__text";
  text.textContent = answer.text;

  el.append(tag, text);
  if (selected || mode === "correct") el.insertAdjacentHTML("beforeend", CHECK_SVG);

  if (interactive) {
    el.addEventListener("click", () => {
      state.selected[question.id] = answer.id;
      saveState();
      render();
    });
  }
  return el;
}

// The quiz while it's being taken: one question at a time.
function renderQuestion(container) {
  const q = QZ.questions[state.index];
  const heading = document.createElement("h2");
  heading.className = "qz-question";
  heading.textContent = q.text;
  container.appendChild(heading);

  const options = document.createElement("div");
  options.className = "qz-options";
  q.answers.forEach((a, ai) => {
    options.appendChild(
      optionEl(q, a, LETTERS[ai], state.selected[q.id] === a.id, "", true)
    );
  });
  container.appendChild(options);
}

// The marked quiz: every question with the visitor's answer and the
// right one, so the whole paper can be read back.
function renderReview(container) {
  QZ.questions.forEach((q, qi) => {
    const result = resultFor(q.id);
    const block = document.createElement("section");
    block.className = "qz-review";

    const heading = document.createElement("h2");
    heading.className = "qz-question";
    heading.textContent = `${qi + 1}. ${q.text}`;
    block.appendChild(heading);

    const options = document.createElement("div");
    options.className = "qz-options";
    q.answers.forEach((a, ai) => {
      const selected = state.selected[q.id] === a.id;
      let mode = "";
      if (result) {
        if (a.id === result.correct_answer_id) mode = "correct";
        else if (selected) mode = "wrong";
      }
      options.appendChild(optionEl(q, a, LETTERS[ai], selected, mode, false));
    });
    block.appendChild(options);
    container.appendChild(block);
  });
}

function renderProgress() {
  const step = document.getElementById("qz-step");
  const note = document.getElementById("qz-note");
  const bars = document.getElementById("qz-bars");
  const total = QZ.questions.length;
  const answered = Object.keys(state.selected).length;

  bars.innerHTML = "";
  QZ.questions.forEach((q, qi) => {
    const bar = document.createElement("div");
    bar.className = "qz-bar";
    if (state.results) {
      const result = resultFor(q.id);
      bar.classList.add(result && result.correct ? "is-correct" : "is-wrong");
    } else if (qi <= state.index || state.selected[q.id] !== undefined) {
      bar.classList.add("is-done");
    }
    bars.appendChild(bar);
  });

  if (state.results) {
    step.textContent = "Answers";
    note.textContent = `${state.results.score} of ${state.results.total} correct`;
    document.getElementById("quiz-status").textContent =
      `Score ${state.results.score}/${state.results.total}`;
  } else {
    step.textContent = `Question ${state.index + 1} of ${total}`;
    note.textContent = "";
    document.getElementById("quiz-status").textContent = `Answered ${answered}/${total}`;
  }
}

function render() {
  const container = document.getElementById("questions");
  container.innerHTML = "";

  const backBtn = document.getElementById("back-btn");
  const nextBtn = document.getElementById("next-btn");
  const retakeBtn = document.getElementById("retake-btn");
  const resultEl = document.getElementById("quiz-result");

  if (state.results) {
    renderReview(container);
    backBtn.hidden = true;
    nextBtn.hidden = true;
    retakeBtn.hidden = false;
    resultEl.hidden = false;
    resultEl.textContent = `You scored ${state.results.score} out of ${state.results.total}.`;
  } else {
    renderQuestion(container);
    const last = state.index === QZ.questions.length - 1;
    backBtn.hidden = state.index === 0;
    nextBtn.hidden = false;
    nextBtn.textContent = last ? "Finish and see answers" : "Next question";
    // Nothing to submit or advance to until this question is answered.
    nextBtn.disabled = state.selected[QZ.questions[state.index].id] === undefined;
    retakeBtn.hidden = true;
    resultEl.hidden = true;
  }

  renderProgress();
}

async function submit() {
  const resp = await fetch(QZ.checkUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": QZ.csrfToken },
    body: JSON.stringify({ answers: state.selected }),
  });
  if (!resp.ok) return;
  state.results = await resp.json();
  saveState();
  render();
  window.scrollTo({ top: 0 });
}

document.getElementById("next-btn").addEventListener("click", () => {
  if (state.index === QZ.questions.length - 1) {
    submit();
    return;
  }
  state.index++;
  saveState();
  render();
});

document.getElementById("back-btn").addEventListener("click", () => {
  if (state.index === 0) return;
  state.index--;
  saveState();
  render();
});

document.getElementById("retake-btn").addEventListener("click", () => {
  state.selected = {};
  state.index = 0;
  state.results = null;
  saveState();
  render();
});

loadState();
render();
