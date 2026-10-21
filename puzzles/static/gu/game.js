"use strict";

// Shared by the games: the splash each one opens on, the sound, the
// confetti for a win, and the GroundUp news shown once a game is over.
window.GU = (() => {
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  // --- Sound ---
  // Synthesised with the Web Audio API rather than played from files, so
  // every game gets the same set. Browsers only allow audio after a click,
  // so the context is created on Start (or on the sound button). One
  // setting for every game: muting one mutes them all.
  const SOUND_KEY = "gu-sound";
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

  const sounds = {
    tap: () => play([[880, 0, 0.05]], "sine", 0.08),
    start: () => play([[392, 0, 0.12], [523, 0.1, 0.12], [784, 0.2, 0.3]]),
    win: () =>
      play([[523, 0, 0.18], [659, 0.15, 0.18], [784, 0.3, 0.18], [1047, 0.45, 0.18], [784, 0.63, 0.14], [1047, 0.77, 0.8]]),
  };

  const soundBtn = document.querySelector(".gu-sound-btn");

  function renderSoundButton() {
    soundBtn.setAttribute("aria-pressed", soundOn);
    soundBtn.querySelector("i").className = `fa-solid ${soundOn ? "fa-volume-high" : "fa-volume-xmark"}`;
  }

  if (soundBtn) {
    renderSoundButton();
    soundBtn.addEventListener("click", () => {
      soundOn = !soundOn;
      try {
        localStorage.setItem(SOUND_KEY, soundOn ? "on" : "off");
      } catch (_) {}
      unlockAudio();
      renderSoundButton();
      sounds.tap();
    });
  }

  // --- Confetti ---
  const CONFETTI = ["#9b3d8f", "#00B1F0", "#F7C600", "#1f8a5b", "#d4582f", "#4d57c4"];

  function confetti() {
    if (reducedMotion) return;
    const layer = document.createElement("div");
    layer.className = "gu-confetti";
    for (let i = 0; i < 90; i++) {
      const bit = document.createElement("span");
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

  function win() {
    sounds.win();
    confetti();
  }

  // --- Splash ---
  // The page is served with body.is-splash, which hides everything else in
  // <main>. Start (Continue, once begun) takes the splash away and calls
  // onStart; the playbar's How to play button, where there is one, brings
  // it back and calls onPause. A game that's already finished calls
  // skip() instead of show(), straight to the result.
  function splash({ begun, onStart = () => {}, onPause = () => {} }) {
    const startBtn = document.getElementById("gu-start");
    const rulesBtn = document.getElementById("gu-rules-btn");

    function show() {
      onPause();
      startBtn.textContent = begun() ? "Continue" : "Start";
      document.body.classList.add("is-splash");
    }

    function skip() {
      document.body.classList.remove("is-splash");
      onStart();
    }

    startBtn.addEventListener("click", () => {
      unlockAudio();
      sounds.start();
      skip();
      window.scrollTo({ top: 0 });
    });
    if (rulesBtn) rulesBtn.addEventListener("click", show);
    return { show, skip };
  }

  // --- Sharing ---
  // The phone's share sheet where there is one, otherwise the clipboard,
  // with the button saying which happened.
  async function share(button, text) {
    const label = button.textContent;
    try {
      if (navigator.share && window.matchMedia("(pointer: coarse)").matches) {
        await navigator.share({ text });
        return;
      }
      await navigator.clipboard.writeText(text);
      button.textContent = "Copied to clipboard";
    } catch (error) {
      if (error.name === "AbortError") return;
      button.textContent = "Couldn't share. Try again.";
    }
    setTimeout(() => (button.textContent = label), 2000);
  }

  // --- GroundUp news ---
  // A news fragment from the puzzles site (see the news_* views), fetched
  // once however often it's asked for. "" if there's nothing to show: no
  // news is fine, the game is what matters.
  const fragments = new Map();
  function fragment(url) {
    if (!fragments.has(url)) {
      fragments.set(
        url,
        fetch(url)
          .then((resp) => (resp.ok ? resp.text() : ""))
          .then((html) => html.trim())
          .catch(() => "")
      );
    }
    return fragments.get(url);
  }

  // Fills news slots (each one's data-news says from where) and shows
  // them, once each: refilling would wipe an email half-typed into the
  // newsletter box. One that comes back empty stays as it was.
  function fill(slots) {
    slots.forEach(async (slot) => {
      if (slot.dataset.filled) return;
      slot.dataset.filled = "yes";
      const html = await fragment(slot.dataset.news);
      if (!html) return;
      slot.innerHTML = html;
      slot.hidden = false;
    });
  }

  // What a game calls once it's over -- as often as it likes.
  function news() {
    fill(document.querySelectorAll(".gu-news"));
  }

  return {
    reducedMotion,
    soundOn: () => soundOn,
    play,
    sounds,
    confetti,
    win,
    splash,
    share,
    fill,
    news,
  };
})();
