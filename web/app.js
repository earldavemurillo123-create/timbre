// Timbre web studio. Plain JavaScript, no build step.

const $ = (sel, root = document) => root.querySelector(sel);

const LANGUAGE_NAMES = {
  en: "English", es: "Spanish", fr: "French", de: "German", it: "Italian", pt: "Portuguese",
  pl: "Polish", tr: "Turkish", ru: "Russian", nl: "Dutch", cs: "Czech", ar: "Arabic",
  "zh-cn": "Chinese", ja: "Japanese", hu: "Hungarian", ko: "Korean", hi: "Hindi",
};

const state = {
  engine: null,
  voices: [],
  selectedId: null,
  mode: "single",
  drafts: { single: "", batch: "" },
  busy: false,
};

const store = {
  get(key, fallback) {
    try { const v = localStorage.getItem(`timbre:${key}`); return v === null ? fallback : JSON.parse(v); }
    catch { return fallback; }
  },
  set(key, value) {
    try { localStorage.setItem(`timbre:${key}`, JSON.stringify(value)); } catch { /* storage unavailable */ }
  },
};

// ------------------------------------------------------------------ API

async function api(path, options = {}) {
  const res = await fetch(path, options);
  if (!res.ok) {
    let message = `Request failed (${res.status}).`;
    try {
      const body = await res.json();
      if (typeof body.detail === "string") message = body.detail;
      else if (Array.isArray(body.detail)) message = body.detail.map((d) => d.msg).join(" ");
    } catch { /* not JSON */ }
    throw new Error(message);
  }
  return res.status === 204 ? null : res.json();
}

const postJSON = (path, data) =>
  api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(data) });

// ------------------------------------------------------------------ waveforms

let audioCtx;
const peakCache = new Map();

async function decodeAudio(arrayBuffer) {
  audioCtx ??= new (window.AudioContext || window.webkitAudioContext)();
  return audioCtx.decodeAudioData(arrayBuffer);
}

function peaksFromDecoded(decoded, bars = 160) {
  const data = decoded.getChannelData(0);
  const size = Math.max(1, Math.floor(data.length / bars));
  const peaks = new Float32Array(bars);
  for (let i = 0; i < bars; i++) {
    let sum = 0;
    const start = i * size;
    for (let j = 0; j < size; j++) { const v = data[start + j] || 0; sum += v * v; }
    peaks[i] = Math.sqrt(sum / size);
  }
  const max = Math.max(...peaks, 1e-4);
  return { peaks: peaks.map((p) => Math.pow(p / max, 0.7)), duration: decoded.duration };
}

async function peaksFromBuffer(arrayBuffer, bars = 160) {
  return peaksFromDecoded(await decodeAudio(arrayBuffer), bars);
}

// Convert decoded audio to a mono 16-bit WAV at 22.05 kHz, so the server can read
// browser recordings (WebM/Ogg) and MP3/M4A files without needing ffmpeg.
async function toWav(decoded, sampleRate = 22050) {
  const length = Math.ceil(decoded.duration * sampleRate);
  const offline = new OfflineAudioContext(1, length, sampleRate);
  const source = offline.createBufferSource();
  source.buffer = decoded;
  source.connect(offline.destination); // mixes all channels down to mono
  source.start();
  const rendered = await offline.startRendering();
  const samples = rendered.getChannelData(0);

  const buffer = new ArrayBuffer(44 + samples.length * 2);
  const view = new DataView(buffer);
  const text = (offset, str) => { for (let i = 0; i < str.length; i++) view.setUint8(offset + i, str.charCodeAt(i)); };
  text(0, "RIFF"); view.setUint32(4, 36 + samples.length * 2, true); text(8, "WAVE");
  text(12, "fmt "); view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true); view.setUint16(34, 16, true);
  text(36, "data"); view.setUint32(40, samples.length * 2, true);
  for (let i = 0; i < samples.length; i++) {
    const v = Math.max(-1, Math.min(1, samples[i]));
    view.setInt16(44 + i * 2, v < 0 ? v * 0x8000 : v * 0x7fff, true);
  }
  return new Blob([buffer], { type: "audio/wav" });
}

async function peaksFromUrl(url, bars) {
  const key = `${url}|${bars}`;
  if (!peakCache.has(key)) {
    peakCache.set(key, fetch(url).then((r) => r.arrayBuffer()).then((b) => peaksFromBuffer(b, bars)));
  }
  return peakCache.get(key);
}

function drawWave(canvas, peaks, { progress = 0, base, played, gap = 2 } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const { width, height } = canvas.getBoundingClientRect();
  if (!width || !height) return;
  canvas.width = Math.round(width * dpr);
  canvas.height = Math.round(height * dpr);
  const ctx = canvas.getContext("2d");
  ctx.scale(dpr, dpr);
  ctx.clearRect(0, 0, width, height);

  const n = peaks.length;
  const slot = width / n;
  const barW = Math.max(1, slot - gap);
  const mid = height / 2;
  for (let i = 0; i < n; i++) {
    const h = Math.max(2, peaks[i] * (height - 4));
    ctx.fillStyle = i / n < progress ? played : base;
    const x = i * slot + (slot - barW) / 2;
    roundRect(ctx, x, mid - h / 2, barW, h, Math.min(barW / 2, 3));
  }
}

function roundRect(ctx, x, y, w, h, r) {
  ctx.beginPath();
  if (ctx.roundRect) ctx.roundRect(x, y, w, h, r);
  else ctx.rect(x, y, w, h);
  ctx.fill();
}

const COLORS = {
  print: { base: "#3d63e6", played: "#ffffff", gap: 4 },
  take: { base: "#b9c3d6", played: "#2357ff", gap: 2 },
  dialog: { base: "#7fa0ff", played: "#7fa0ff" },
};

// ------------------------------------------------------------------ shared player

const player = {
  audio: new Audio(),
  owner: null, // { url, button, canvas, peaks, colors }

  async toggle(owner) {
    if (this.owner && this.owner.url === owner.url) {
      if (this.audio.paused) await this.audio.play(); else this.audio.pause();
      return;
    }
    this.stop();
    this.owner = owner;
    this.audio.src = owner.url;
    await this.audio.play().catch(() => toast("Couldn't play this file."));
  },

  seek(owner, fraction) {
    const go = () => { this.audio.currentTime = fraction * (this.audio.duration || 0); };
    if (this.owner?.url !== owner.url) {
      this.toggle(owner).then(() => { if (this.audio.readyState >= 1) go(); else this.audio.addEventListener("loadedmetadata", go, { once: true }); });
    } else go();
  },

  stop() {
    this.audio.pause();
    if (this.owner) {
      this.owner.button?.removeAttribute("data-playing");
      this.redraw(0);
    }
    this.owner = null;
  },

  redraw(progress) {
    const o = this.owner;
    if (o?.canvas && o.peaks) drawWave(o.canvas, o.peaks, { progress, ...o.colors });
  },

  tick() {
    if (player.owner && !player.audio.paused) {
      player.redraw(player.audio.currentTime / (player.audio.duration || 1));
      requestAnimationFrame(player.tick);
    }
  },
};

player.audio.addEventListener("play", () => { player.owner?.button?.setAttribute("data-playing", ""); requestAnimationFrame(player.tick); });
player.audio.addEventListener("pause", () => player.owner?.button?.removeAttribute("data-playing"));
player.audio.addEventListener("ended", () => { player.redraw(0); player.owner?.button?.removeAttribute("data-playing"); });

function bindWaveSeek(canvas, getOwner) {
  canvas.addEventListener("click", (e) => {
    const owner = getOwner();
    if (!owner) return;
    const rect = canvas.getBoundingClientRect();
    player.seek(owner, (e.clientX - rect.left) / rect.width);
  });
}

// ------------------------------------------------------------------ toast

let toastTimer;
function toast(message) {
  const el = $("#toast");
  el.textContent = message;
  el.setAttribute("data-show", "");
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => el.removeAttribute("data-show"), 2600);
}

// ------------------------------------------------------------------ engine status

async function loadStatus() {
  const pill = $("#engine");
  try {
    const status = await api("/api/status");
    state.engine = status.engine;
    const { label, device, is_demo: isDemo, languages } = status.engine;
    pill.dataset.state = isDemo ? "demo" : status.ready ? "ready" : "loading";
    $("#engine-text").textContent = `${label} on ${device.toUpperCase()}`;
    $("#demo-note").hidden = !isDemo;

    const select = $("#language");
    const saved = store.get("language", "en");
    select.replaceChildren(...languages.map((code) => new Option(LANGUAGE_NAMES[code] || code, code, false, code === saved)));
  } catch {
    pill.dataset.state = "error";
    $("#engine-text").textContent = "Engine offline. Is the server running?";
  }
}

// ------------------------------------------------------------------ voices

const TRASH = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" aria-hidden="true"><path d="M4 7h16M10 11v6M14 11v6M6 7l1 13h10l1-13M9 7V4h6v3"/></svg>';

async function loadVoices() {
  state.voices = await api("/api/voices");
  const saved = store.get("voice", null);
  if (!state.voices.some((v) => v.id === state.selectedId)) {
    state.selectedId = state.voices.find((v) => v.id === saved)?.id ?? state.voices[0]?.id ?? null;
  }
  renderVoices();
}

function renderVoices() {
  const list = $("#voice-list");
  list.replaceChildren(...state.voices.map((voice) => {
    const li = document.createElement("li");
    li.className = "voice";
    li.innerHTML = `
      <button class="voice__pick" type="button" aria-pressed="${voice.id === state.selectedId}">
        <span class="voice__name"></span>
        <span class="voice__len">${voice.duration.toFixed(1)} s clip</span>
      </button>
      <button class="voice__delete" type="button" aria-label="Delete voice ${escapeAttr(voice.name)}">${TRASH}</button>`;
    $(".voice__name", li).textContent = voice.name;
    $(".voice__pick", li).addEventListener("click", () => selectVoice(voice.id));
    $(".voice__delete", li).addEventListener("click", () => deleteVoice(voice));
    return li;
  }));
  renderPrint();
  updateGenerateState();
}

function selectVoice(id) {
  state.selectedId = id;
  store.set("voice", id);
  player.stop();
  renderVoices();
}

async function deleteVoice(voice) {
  if (!confirm(`Delete the voice "${voice.name}"? Takes made with it are kept.`)) return;
  try {
    await api(`/api/voices/${voice.id}`, { method: "DELETE" });
    if (state.selectedId === voice.id) state.selectedId = null;
    await loadVoices();
    toast(`Deleted ${voice.name}`);
  } catch (err) { toast(err.message); }
}

let printOwner = null;

async function renderPrint() {
  const print = $("#print");
  const voice = state.voices.find((v) => v.id === state.selectedId);
  $("#print-empty").hidden = Boolean(voice);
  $("#print-meta").hidden = !voice;
  print.toggleAttribute("data-empty", !voice);
  if (!voice) { printOwner = null; return; }

  $("#print-name").textContent = voice.name;
  const added = new Date(voice.created_at * 1000).toLocaleDateString(undefined, { month: "short", day: "numeric" });
  $("#print-detail").textContent = `${voice.duration.toFixed(1)} seconds of reference speech, added ${added}`;

  const url = `/api/voices/${voice.id}/audio`;
  const canvas = $("#print-wave");
  printOwner = { url, button: $("#print-play"), canvas, peaks: null, colors: COLORS.print };
  const owner = printOwner;
  try {
    const { peaks } = await peaksFromUrl(url, 64);
    owner.peaks = peaks;
    if (printOwner === owner) drawWave(canvas, peaks, COLORS.print);
  } catch { /* browser couldn't decode; leave blank */ }
}

// ------------------------------------------------------------------ script + generate

function setMode(mode) {
  const text = $("#script-text");
  state.drafts[state.mode] = text.value;
  state.mode = mode;
  text.value = state.drafts[mode];
  document.querySelectorAll(".modes__tab").forEach((tab) => tab.setAttribute("aria-selected", tab.dataset.mode === mode));
  $("#panel-text").setAttribute("aria-labelledby", `tab-${mode}`);
  if (mode === "batch") {
    text.placeholder = "One line per clip.\n# Lines starting with # are notes and get skipped.\nIn this town, nobody sleeps.\nNot even the mayor.";
    $("#script-hint").textContent = "Each line becomes its own clip. You also get all lines joined into one file, with subtitles.";
    $("#generate-label").textContent = "Generate script";
  } else {
    text.placeholder = "Write what the voice should say.";
    $("#script-hint").textContent = "Long text is split into sentences and joined with short pauses.";
    $("#generate-label").textContent = "Generate take";
  }
  updateCounter();
}

function updateCounter() {
  const len = $("#script-text").value.length;
  const counter = $("#counter");
  if (state.mode === "batch") {
    const lines = $("#script-text").value.split("\n").filter((l) => l.trim() && !l.trim().startsWith("#")).length;
    counter.textContent = `${lines} ${lines === 1 ? "line" : "lines"}`;
    counter.removeAttribute("data-over");
  } else {
    counter.textContent = `${len} / 5000`;
    counter.toggleAttribute("data-over", len > 5000);
  }
  updateGenerateState();
}

function updateGenerateState() {
  const hasText = $("#script-text").value.trim().length > 0;
  $("#generate-btn").disabled = state.busy || !state.selectedId || !hasText;
}

async function generate(event) {
  event?.preventDefault();
  if ($("#generate-btn").disabled) return;
  const error = $("#generate-error");
  error.hidden = true;

  const payload = {
    voice_id: state.selectedId,
    language: $("#language").value,
    speed: Number($("#speed").value),
  };
  const text = $("#script-text").value;
  const isBatch = state.mode === "batch";
  if (isBatch) payload.script = text; else payload.text = text;

  state.busy = true;
  const btn = $("#generate-btn");
  btn.setAttribute("data-busy", "");
  const label = $("#generate-label");
  const original = label.textContent;
  label.textContent = "Generating…";
  updateGenerateState();

  try {
    const take = await postJSON(isBatch ? "/api/batch" : "/api/speak", payload);
    const row = renderTake(take, true);
    $("#take-list").prepend(row);
    toast(`Take ${take.number} is ready`);
  } catch (err) {
    error.textContent = err.message;
    error.hidden = false;
  } finally {
    state.busy = false;
    btn.removeAttribute("data-busy");
    label.textContent = original;
    updateGenerateState();
  }
}

// ------------------------------------------------------------------ takes

const waveObserver = new IntersectionObserver((entries) => {
  for (const entry of entries) {
    if (!entry.isIntersecting) continue;
    waveObserver.unobserve(entry.target);
    entry.target.__drawWave?.();
  }
}, { rootMargin: "200px" });

async function loadTakes() {
  try {
    const takes = await api("/api/takes");
    $("#take-list").replaceChildren(...takes.map((t) => renderTake(t)));
  } catch { /* server offline; status pill already says so */ }
}

function renderTake(take, fresh = false) {
  const base = `/api/takes/${take.id}`;
  const url = `${base}/${take.files.audio}`;
  const li = document.createElement("li");
  li.className = "take";
  if (fresh) li.setAttribute("data-fresh", "");
  const lang = LANGUAGE_NAMES[take.language] || take.language;
  const kind = take.kind === "batch" ? `${take.lines.length} lines, ` : "";

  li.innerHTML = `
    <p class="take__no"><small>Take</small>${take.number}</p>
    <button class="play" type="button" aria-label="Play take ${take.number}">
      <svg viewBox="0 0 24 24" aria-hidden="true"><path class="i-play" d="M8 5.5v13l10.5-6.5z"/><path class="i-pause" d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg>
    </button>
    <div>
      <p class="take__text"></p>
      <p class="take__meta"></p>
    </div>
    <canvas class="take__wave" aria-hidden="true"></canvas>
    <div class="take__actions">
      <a href="${url}?download=true" download>WAV</a>
      <a href="${base}/${take.files.subtitles}?download=true" download>SRT</a>
      <button type="button" aria-label="Delete take ${take.number}">Delete</button>
    </div>`;

  $(".take__text", li).textContent = take.text.replace(/\n/g, " / ");
  $(".take__meta", li).textContent = `${take.voice_name}, ${kind}${take.duration.toFixed(1)} s, ${lang}, ${take.speed.toFixed(2)}×`;

  const canvas = $(".take__wave", li);
  const owner = { url, button: $(".play", li), canvas, peaks: null, colors: COLORS.take };
  canvas.__drawWave = async () => {
    try {
      owner.peaks = (await peaksFromUrl(url, 70)).peaks;
      drawWave(canvas, owner.peaks, COLORS.take);
    } catch { /* ignore */ }
  };
  waveObserver.observe(canvas);
  $(".play", li).addEventListener("click", () => player.toggle(owner));
  bindWaveSeek(canvas, () => owner);

  $(".take__actions button", li).addEventListener("click", async () => {
    if (!confirm(`Delete take ${take.number}? Its audio and subtitle files are removed.`)) return;
    try {
      if (player.owner?.url === url) player.stop();
      await api(base, { method: "DELETE" });
      li.remove();
      toast(`Deleted take ${take.number}`);
    } catch (err) { toast(err.message); }
  });
  return li;
}

// ------------------------------------------------------------------ add-voice dialog

const dialog = $("#voice-dialog");
const clip = { blob: null, filename: null };
const rec = { recorder: null, stream: null, chunks: [], timer: null, started: 0, raf: 0 };
const MAX_RECORD_SECONDS = 30;

function openDialog() {
  clip.blob = null; clip.filename = null;
  $("#voice-form").reset();
  $("#voice-error").hidden = true;
  $("#clip-info").textContent = "Clean speech works best: one speaker, no music, little echo.";
  $("#rec-time").textContent = "0:00";
  dialog.showModal();
  clearDialogWave();
  $("#voice-name").focus();
}

function clearDialogWave() {
  const canvas = $("#dialog-wave");
  drawWave(canvas, new Float32Array(90).fill(0.02), COLORS.dialog);
}

async function useClip(blob, filename) {
  clip.blob = blob; clip.filename = filename;
  const isWav = /\.wav$/i.test(filename) || blob.type === "audio/wav";
  try {
    const decoded = await decodeAudio(await blob.arrayBuffer());
    const { peaks, duration } = peaksFromDecoded(decoded, 90);
    drawWave($("#dialog-wave"), peaks, COLORS.dialog);
    if (!isWav) {
      clip.blob = await toWav(decoded);
      clip.filename = filename.replace(/\.[^.]+$/, "") + ".wav";
    }
    const hint = duration < 6 ? " That's short; 10–30 seconds gives a closer match." :
                 duration > 30 ? " Only the first 30 seconds of speech are used." : "";
    $("#clip-info").textContent = `${filename}, ${duration.toFixed(1)} seconds.${hint}`;
  } catch {
    $("#clip-info").textContent = `${filename}. Your browser can't read this format; if saving fails, upload a .wav file.`;
  }
  if (!$("#voice-name").value.trim()) {
    $("#voice-name").value = filename.replace(/\.[^.]+$/, "").replace(/[-_]+/g, " ").slice(0, 60);
  }
}

$("#voice-file").addEventListener("change", (e) => {
  const file = e.target.files[0];
  if (file) useClip(file, file.name);
});

const drop = $("#drop");
drop.addEventListener("dragover", (e) => { e.preventDefault(); drop.setAttribute("data-over", ""); });
drop.addEventListener("dragleave", () => drop.removeAttribute("data-over"));
drop.addEventListener("drop", (e) => {
  e.preventDefault();
  drop.removeAttribute("data-over");
  const file = e.dataTransfer.files[0];
  if (file) useClip(file, file.name);
});

$("#rec-btn").addEventListener("click", () => (rec.recorder ? stopRecording() : startRecording()));

async function startRecording() {
  try {
    rec.stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: true, noiseSuppression: true } });
  } catch {
    showVoiceError("Microphone access was blocked. Allow it in your browser's site settings, or upload a clip instead.");
    return;
  }
  rec.chunks = [];
  rec.recorder = new MediaRecorder(rec.stream);
  rec.recorder.ondataavailable = (e) => e.data.size && rec.chunks.push(e.data);
  rec.recorder.onstop = () => {
    const type = rec.recorder.mimeType || "audio/webm";
    const ext = type.includes("ogg") ? "ogg" : type.includes("mp4") ? "m4a" : "webm";
    const blob = new Blob(rec.chunks, { type });
    rec.stream.getTracks().forEach((t) => t.stop());
    rec.recorder = null;
    useClip(blob, `recording.${ext}`);
  };
  rec.recorder.start();
  rec.started = performance.now();

  const btn = $("#rec-btn");
  btn.setAttribute("aria-pressed", "true");
  $("#rec-label").textContent = "Stop";
  $("#clip-info").textContent = "Recording. Read a few natural sentences in your normal speaking voice.";

  // Live level meter on the dialog waveform.
  audioCtx ??= new (window.AudioContext || window.webkitAudioContext)();
  await audioCtx.resume();
  const analyser = audioCtx.createAnalyser();
  analyser.fftSize = 1024;
  audioCtx.createMediaStreamSource(rec.stream).connect(analyser);
  const levels = new Float32Array(90).fill(0.02);
  const buf = new Float32Array(analyser.fftSize);
  const canvas = $("#dialog-wave");
  const frame = () => {
    if (!rec.recorder) return;
    analyser.getFloatTimeDomainData(buf);
    let sum = 0; for (const v of buf) sum += v * v;
    levels.copyWithin(0, 1);
    levels[levels.length - 1] = Math.min(1, Math.sqrt(sum / buf.length) * 6);
    drawWave(canvas, levels, { base: "#ffffff", played: "#ffffff" });
    const secs = (performance.now() - rec.started) / 1000;
    $("#rec-time").textContent = `0:${String(Math.floor(secs)).padStart(2, "0")}`;
    if (secs >= MAX_RECORD_SECONDS) { stopRecording(); return; }
    rec.raf = requestAnimationFrame(frame);
  };
  rec.raf = requestAnimationFrame(frame);
}

function stopRecording() {
  cancelAnimationFrame(rec.raf);
  $("#rec-btn").setAttribute("aria-pressed", "false");
  $("#rec-label").textContent = "Record again";
  rec.recorder?.stop();
}

function showVoiceError(message) {
  const el = $("#voice-error");
  el.textContent = message;
  el.hidden = false;
}

$("#voice-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#voice-error").hidden = true;
  const name = $("#voice-name").value.trim();
  if (!name) return showVoiceError("Give the voice a name so you can find it later.");
  if (!clip.blob) return showVoiceError("Choose an audio clip or record one first.");
  if (!$("#voice-consent").checked) return showVoiceError("Confirm you have permission to clone this voice.");

  const form = new FormData();
  form.append("name", name);
  form.append("consent", "true");
  form.append("file", clip.blob, clip.filename);

  const save = $("#voice-save");
  save.disabled = true;
  save.textContent = "Saving…";
  try {
    const voice = await api("/api/voices", { method: "POST", body: form });
    dialog.close();
    state.selectedId = voice.id;
    store.set("voice", voice.id);
    await loadVoices();
    toast(`Saved ${voice.name}`);
  } catch (err) {
    showVoiceError(err.message);
  } finally {
    save.disabled = false;
    save.textContent = "Save voice";
  }
});

$("#voice-cancel").addEventListener("click", () => { if (rec.recorder) stopRecording(); dialog.close(); });
dialog.addEventListener("close", () => { if (rec.recorder) stopRecording(); });

// ------------------------------------------------------------------ wiring

function escapeAttr(s) { return s.replace(/[&"<>]/g, (c) => ({ "&": "&amp;", '"': "&quot;", "<": "&lt;", ">": "&gt;" })[c]); }

$("#add-voice-btn").addEventListener("click", openDialog);
$("#empty-add-btn").addEventListener("click", openDialog);
$("#print-play").addEventListener("click", () => printOwner && player.toggle(printOwner));
bindWaveSeek($("#print-wave"), () => printOwner);

document.querySelectorAll(".modes__tab").forEach((tab) => tab.addEventListener("click", () => setMode(tab.dataset.mode)));
document.querySelector(".modes").addEventListener("keydown", (e) => {
  if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
    const next = state.mode === "single" ? "batch" : "single";
    setMode(next);
    $(`#tab-${next}`).focus();
  }
});

$("#script-text").addEventListener("input", () => {
  updateCounter();
  state.drafts[state.mode] = $("#script-text").value;
  store.set("drafts", state.drafts);
});
$("#script-text").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) generate(e);
});
$("#script-form").addEventListener("submit", generate);

$("#speed").addEventListener("input", (e) => { $("#speed-out").textContent = `${Number(e.target.value).toFixed(2)}×`; });
$("#language").addEventListener("change", (e) => store.set("language", e.target.value));

let resizeTimer;
window.addEventListener("resize", () => {
  clearTimeout(resizeTimer);
  resizeTimer = setTimeout(() => {
    renderPrint();
    document.querySelectorAll(".take__wave").forEach((c) => c.__drawWave?.());
  }, 150);
});

// ------------------------------------------------------------------ start

state.drafts = { single: "", batch: "", ...store.get("drafts", {}) };
$("#script-text").value = state.drafts.single;
updateCounter();
await loadStatus();
await Promise.all([loadVoices().catch(() => {}), loadTakes()]);
