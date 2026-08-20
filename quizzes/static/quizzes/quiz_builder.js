"use strict";

// In-memory model mirrors the server: quiz_save always deletes and
// recreates every Question/Answer row from this list, so (unlike the
// crossword editor) there's no separate "source of truth" grid to keep in
// sync -- this state *is* what gets saved, verbatim, in display order.
const QZ = window.QUIZ;

const state = {
  questions: QZ.questions.map((q) => ({
    text: q.text,
    answers: q.answers.map((a) => ({ text: a.text, correct: a.correct })),
  })),
};

let dirty = false;
function markDirty() {
  dirty = true;
}

function moveItem(list, index, delta) {
  const target = index + delta;
  if (target < 0 || target >= list.length) return;
  [list[index], list[target]] = [list[target], list[index]];
  markDirty();
  render();
}

// A small icon-only button (Font Awesome glyph + title tooltip), used for
// the up/down/delete controls on questions and answers.
function iconButton(iconClass, title, onClick, extraClass) {
  const btn = document.createElement("button");
  btn.type = "button";
  btn.className = "icon-btn" + (extraClass ? " " + extraClass : "");
  btn.title = title;
  btn.setAttribute("aria-label", title);
  btn.innerHTML = `<i class="fa-solid ${iconClass}"></i>`;
  btn.addEventListener("click", onClick);
  return btn;
}

// Rebuilds the whole question list from state. Small enough (a handful of
// questions/answers, all plain DOM) that a full rebuild on every change is
// simpler than tracking incremental updates, same rationale as the
// crossword editor's render().
function render() {
  const container = document.getElementById("questions");
  container.innerHTML = "";

  state.questions.forEach((q, qi) => {
    const block = document.createElement("div");
    block.className = "question-block";

    const header = document.createElement("div");
    header.className = "question-header";

    const number = document.createElement("span");
    number.className = "question-number";
    number.textContent = `Q${qi + 1}`;

    const textInput = document.createElement("input");
    textInput.type = "text";
    textInput.className = "question-text";
    textInput.placeholder = "Question text";
    textInput.value = q.text;
    textInput.addEventListener("input", (e) => {
      q.text = e.target.value;
      markDirty();
    });

    const upBtn = iconButton("fa-arrow-up", "Move question up", () =>
      moveItem(state.questions, qi, -1)
    );
    upBtn.disabled = qi === 0;
    const downBtn = iconButton("fa-arrow-down", "Move question down", () =>
      moveItem(state.questions, qi, 1)
    );
    downBtn.disabled = qi === state.questions.length - 1;
    const deleteBtn = iconButton(
      "fa-trash",
      "Delete question",
      () => {
        state.questions.splice(qi, 1);
        markDirty();
        render();
      },
      "btn-delete"
    );

    header.append(number, textInput, upBtn, downBtn, deleteBtn);
    block.appendChild(header);

    // Non-blocking: flags a question with no correct answer marked yet,
    // but never stops the setter from saving (they may want to add a
    // wrong answer before deciding on the right one).
    if (!q.answers.some((a) => a.correct)) {
      const warning = document.createElement("p");
      warning.className = "warning";
      warning.textContent = "No correct answer selected yet.";
      block.appendChild(warning);
    }

    const answersList = document.createElement("div");
    answersList.className = "answers-list";
    q.answers.forEach((a, ai) => {
      const row = document.createElement("div");
      row.className = "answer-row";

      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = `correct-${qi}`;
      radio.checked = a.correct;
      radio.title = "Correct answer";
      radio.addEventListener("change", () => {
        q.answers.forEach((other, oi) => (other.correct = oi === ai));
        markDirty();
        render();
      });

      const answerInput = document.createElement("input");
      answerInput.type = "text";
      answerInput.className = "answer-text";
      answerInput.placeholder = "Answer text";
      answerInput.value = a.text;
      answerInput.addEventListener("input", (e) => {
        a.text = e.target.value;
        markDirty();
      });

      const upA = iconButton("fa-arrow-up", "Move answer up", () =>
        moveItem(q.answers, ai, -1)
      );
      upA.disabled = ai === 0;
      const downA = iconButton("fa-arrow-down", "Move answer down", () =>
        moveItem(q.answers, ai, 1)
      );
      downA.disabled = ai === q.answers.length - 1;
      const deleteA = iconButton(
        "fa-trash",
        "Delete answer",
        () => {
          q.answers.splice(ai, 1);
          markDirty();
          render();
        },
        "btn-delete"
      );

      row.append(radio, answerInput, upA, downA, deleteA);
      answersList.appendChild(row);
    });
    block.appendChild(answersList);

    const addAnswerBtn = document.createElement("button");
    addAnswerBtn.type = "button";
    addAnswerBtn.className = "add-answer-btn";
    addAnswerBtn.textContent = "Add answer";
    addAnswerBtn.addEventListener("click", () => {
      q.answers.push({ text: "", correct: false });
      markDirty();
      render();
    });
    block.appendChild(addAnswerBtn);

    container.appendChild(block);
  });
}

document.getElementById("add-question-btn").addEventListener("click", () => {
  state.questions.push({ text: "", answers: [] });
  markDirty();
  render();
});

// --- Publish status (mirrors the crossword editor's publish controls) ---
function updatePublishStatus() {
  const val = document.getElementById("qz-published").value;
  const span = document.getElementById("publish-status");
  const btn = document.getElementById("publish-btn");
  const isPublished = val && new Date(val) <= new Date();
  span.textContent = isPublished ? "Published" : "Unpublished";
  span.className = isPublished ? "status-published" : "status-unpublished";
  btn.textContent = isPublished ? "Unpublish" : "Publish";
}

function nowLocalISO() {
  const d = new Date();
  const pad = (n) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function localISOWithOffset(localIsoStr) {
  const off = -new Date().getTimezoneOffset();
  const sign = off >= 0 ? "+" : "-";
  const pad = (n) => String(n).padStart(2, "0");
  const offH = pad(Math.floor(Math.abs(off) / 60));
  const offM = pad(Math.abs(off) % 60);
  return `${localIsoStr}:00${sign}${offH}:${offM}`;
}

document.getElementById("publish-btn").addEventListener("click", () => {
  const input = document.getElementById("qz-published");
  const isPublished = input.value && new Date(input.value) <= new Date();
  input.value = isPublished ? "" : nowLocalISO();
  markDirty();
  updatePublishStatus();
});

// --- Save ---
document.getElementById("save-btn").addEventListener("click", async () => {
  const body = {
    name: document.getElementById("qz-name").value,
    description: document.getElementById("qz-description").value,
    authors: document.getElementById("qz-authors").value,
    editors: document.getElementById("qz-editors").value,
    copyright: document.getElementById("qz-copyright").value,
    published: document.getElementById("qz-published").value
      ? localISOWithOffset(document.getElementById("qz-published").value)
      : null,
    questions: state.questions,
  };
  const resp = await fetch(QZ.saveUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json", "X-CSRFToken": QZ.csrfToken },
    body: JSON.stringify(body),
  });
  const btn = document.getElementById("save-btn");
  if (resp.ok) {
    updatePublishStatus();
    dirty = false;
  }
  btn.textContent = resp.ok ? "Saved" : "Save failed";
  setTimeout(() => (btn.textContent = "Save"), 1500);
});

render();
updatePublishStatus();

["qz-name", "qz-authors", "qz-editors", "qz-copyright", "qz-description", "qz-published"].forEach(
  (id) => document.getElementById(id).addEventListener("input", markDirty)
);

// Triggers the browser's native "leave site?" confirmation on tab close/
// reload when there are unsaved changes (mirrors the crossword editor).
window.addEventListener("beforeunload", (e) => {
  if (dirty) e.preventDefault();
});
