"use strict";

const QZ = window.QUIZ;

// Progress is saved to localStorage per quiz, same rationale as the
// crossword solver: reloading or returning later restores exactly where
// the solver left off, including a completed result.
const STORAGE_KEY = `quiz-solver-${QZ.pk}`;

const state = {
  selected: {}, // question id -> selected answer id
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

// Rebuilds the whole question list from state. Called after every change;
// cheap enough (a handful of questions/answers, all plain DOM) that a full
// rebuild is simpler than tracking incremental updates.
function render() {
  const container = document.getElementById("questions");
  container.innerHTML = "";

  QZ.questions.forEach((q, qi) => {
    const block = document.createElement("div");
    block.className = "question-block";

    const header = document.createElement("div");
    header.className = "question-header";
    const number = document.createElement("span");
    number.className = "question-number";
    number.textContent = `Q${qi + 1}`;
    const text = document.createElement("span");
    text.className = "question-text";
    text.textContent = q.text;
    header.append(number, text);
    block.appendChild(header);

    const result = resultFor(q.id);

    const answersList = document.createElement("div");
    answersList.className = "answers-list";
    q.answers.forEach((a) => {
      const row = document.createElement("label");
      row.className = "answer-row";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `question-${q.id}`;
      radio.checked = state.selected[q.id] === a.id;
      radio.disabled = !!state.results;
      radio.addEventListener("change", () => {
        state.selected[q.id] = a.id;
        saveState();
      });

      const answerText = document.createElement("span");
      answerText.className = "answer-text";
      answerText.textContent = a.text;

      row.append(radio, answerText);

      if (result) {
        if (a.id === result.correct_answer_id) row.classList.add("answer-correct");
        else if (a.id === state.selected[q.id]) row.classList.add("answer-wrong");
      }

      answersList.appendChild(row);
    });
    block.appendChild(answersList);
    container.appendChild(block);
  });

  document.getElementById("submit-btn").hidden = !!state.results;
  document.getElementById("retake-btn").hidden = !state.results;

  const resultEl = document.getElementById("quiz-result");
  if (state.results) {
    resultEl.hidden = false;
    resultEl.textContent = `You scored ${state.results.score} out of ${state.results.total}.`;
  } else {
    resultEl.hidden = true;
  }
}

document.getElementById("submit-btn").addEventListener("click", async () => {
  const resp = await fetch(QZ.checkUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": QZ.csrfToken },
    body: JSON.stringify({ answers: state.selected }),
  });
  if (!resp.ok) return;
  state.results = await resp.json();
  saveState();
  render();
});

document.getElementById("retake-btn").addEventListener("click", () => {
  state.selected = {};
  state.results = null;
  saveState();
  render();
});

loadState();
render();
