/* AutoMind web app. No build step, no libraries. */
(() => {
"use strict";
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const MARKER = "---ANSWERS---";
const store = {
  get(k, d) { try { return localStorage.getItem(k) ?? d; } catch { return d; } },
  set(k, v) { try { localStorage.setItem(k, v); } catch { /* private mode */ } },
};
const state = {
  lang: store.get("am.lang", "en"), theme: store.get("am.theme", ""),
  docs: [], selected: new Set(), history: [], busy: false, abort: null,
  tab: "chat", tool: null, md: "", sources: [], practice: false, showAnswers: false,
  model: null, readerDoc: null, readerPages: [], readerPage: 0,
};
if (!I18N[state.lang]) state.lang = "en";

/* ------------------------------------------------------------ helpers */
const t = (k, v = {}) => {
  let s = (I18N[state.lang][k] ?? I18N.en[k] ?? k);
  for (const [a, b] of Object.entries(v)) s = s.replaceAll(`{${a}}`, b);
  return s;
};
const esc = s => String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const hasArabic = s => /[؀-ۿݐ-ݿﭐ-﷿ﹰ-﻿]/.test(s);
function toast(msg, err = false) {
  const el = document.createElement("div");
  el.className = "toast" + (err ? " err" : ""); el.textContent = msg;
  $("#toasts").append(el); setTimeout(() => el.remove(), err ? 6000 : 2800);
}
function errText(body, status) {
  const d = body && body.detail;
  if (Array.isArray(d)) return d.map(x => x.msg || JSON.stringify(x)).join("; ");
  if (typeof d === "string") return d;
  return `${t("errorGeneric")} (${status})`;
}
async function api(path, opts = {}) {
  const res = await fetch(path, opts);
  if (!res.ok) throw new Error(errText(await res.json().catch(() => null), res.status));
  return res.status === 204 ? null : res.json();
}
const post = (path, body) => api(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
async function stream(path, body, handlers, signal) {
  const res = await fetch(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  if (!res.ok) throw new Error(errText(await res.json().catch(() => null), res.status));
  const reader = res.body.getReader(), dec = new TextDecoder(); let buf = "";
  for (;;) {
    const { value, done } = await reader.read(); if (done) break;
    buf += dec.decode(value, { stream: true });
    let i;
    while ((i = buf.indexOf("\n\n")) >= 0) {
      const raw = buf.slice(0, i); buf = buf.slice(i + 2);
      let ev = "message", data = "";
      for (const line of raw.split("\n")) {
        if (line.startsWith("event:")) ev = line.slice(6).trim();
        else if (line.startsWith("data:")) data += line.slice(5).trim();
      }
      if (data) { const h = handlers[ev]; if (h) h(JSON.parse(data)); }
    }
  }
}

/* ------------------------------------------------------------ markdown */
function inline(s) {
  return esc(s).replace(/`([^`]+)`/g, "<code>$1</code>").replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
    .replace(/(^|[^*])\*([^*\n]+)\*/g, "$1<em>$2</em>");
}
function md(src) {
  const out = []; const stack = []; let para = [];
  const flush = () => { if (para.length) { out.push('<p dir="auto">' + para.map(inline).join("<br>") + "</p>"); para = []; } };
  const closeTo = n => { while (stack.length > n) { out.push("</li></" + stack.pop().type + ">"); } };
  for (const raw of src.split("\n")) {
    const line = raw.replace(/\s+$/, "");
    if (!line.trim()) { flush(); continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)$/))) { flush(); closeTo(0); out.push(`<h${Math.min(m[1].length, 3)} dir="auto">${inline(m[2])}</h${Math.min(m[1].length, 3)}>`); continue; }
    if (/^\s*[-*_]{3,}\s*$/.test(line)) { flush(); closeTo(0); out.push("<hr>"); continue; }
    if ((m = line.match(/^>\s?(.*)$/))) { flush(); closeTo(0); out.push('<blockquote dir="auto">' + inline(m[1]) + "</blockquote>"); continue; }
    if ((m = line.match(/^(\s*)([-*•]|\d+[.)])\s+(.*)$/))) {
      flush();
      const indent = m[1].length, type = /\d/.test(m[2]) ? "ol" : "ul";
      while (stack.length && stack[stack.length - 1].indent > indent) out.push("</li></" + stack.pop().type + ">");
      const top = stack[stack.length - 1];
      if (top && top.indent === indent && top.type === type) out.push("</li>");
      else { if (top && top.indent === indent) out.push("</li></" + stack.pop().type + ">"); stack.push({ indent, type }); out.push("<" + type + ">"); }
      out.push(type === "ol" ? `<li dir="auto" value="${parseInt(m[2], 10)}">` : '<li dir="auto">'); out.push(inline(m[3]));
      continue;
    }
    if (stack.length && /^\s+/.test(line)) { out.push("<br>" + inline(line.trim())); continue; }
    closeTo(0); para.push(line.trim());
  }
  flush(); closeTo(0);
  return out.join("");
}
function withCitations(html) {
  return html.replace(/\[(\d+(?:\s*,\s*\d+)*)\]/g, (_, g) => g.split(/\s*,\s*/).map(n => `<button class="cite" data-n="${n}" type="button">${n}</button>`).join(""));
}
function speakable(markdown) {
  return markdown.replace(/```[\s\S]*?```/g, " ").replace(/^#{1,6}\s*/gm, "").replace(/[*_`>]/g, "")
    .replace(/\[\d+(?:\s*,\s*\d+)*\]/g, "").replace(/\((?:p\.|ص)\s*\d+\)/g, "").replace(/_{3,}/g, " blank ")
    .replace(/^\s*[-•]\s+/gm, "").replace(/\s+/g, " ").trim();
}

/* ------------------------------------------------------------ language, theme */
function applyLang() {
  const L = I18N[state.lang];
  document.documentElement.lang = state.lang; document.documentElement.dir = L.dir;
  $$("[data-i18n]").forEach(e => { e.textContent = t(e.dataset.i18n); });
  $$("[data-i18n-ph]").forEach(e => { e.placeholder = t(e.dataset.i18nPh); });
  $$("[data-i18n-title]").forEach(e => { e.title = t(e.dataset.i18nTitle); });
  $$("#langSeg button").forEach(b => b.classList.toggle("on", b.dataset.lang === state.lang));
  renderSuggestions(); renderDocs(); renderTools(); renderModel(); updateOutputBar(); renderReaderControls(); fillProviders();
  if (state.md) renderOutput();
}
function applyTheme() {
  const dark = state.theme ? state.theme === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.dataset.theme = dark ? "dark" : "light";
}

/* ------------------------------------------------------------ documents */
async function loadDocs() {
  try { state.docs = await api("/documents"); } catch (e) { toast(e.message, true); return; }
  const ids = new Set(state.docs.map(d => d.id));
  state.selected = new Set([...state.selected].filter(i => ids.has(i)));
  renderDocs();
}
function renderDocs() {
  const ul = $("#docList"); ul.innerHTML = "";
  if (!state.docs.length) { ul.innerHTML = `<li class="empty-docs">${esc(t("noDocs"))}</li>`; }
  for (const d of state.docs) {
    const li = document.createElement("li"); li.className = "doc" + (state.selected.has(d.id) ? " sel" : "");
    li.innerHTML = `<input type="checkbox" ${state.selected.has(d.id) ? "checked" : ""} aria-label="select">
      <div class="doc-main" title="${esc(t("openReader"))}"><div class="doc-name" dir="auto">${esc(d.filename)}</div>
      <div class="doc-meta">${esc(t("pagesN", { n: d.n_pages }))} · ${(d.size_bytes / 1024).toFixed(0)} KB</div></div>
      <button class="icon-btn" title="${esc(t("deleteDoc"))}" aria-label="delete">🗑</button>`;
    $("input", li).onchange = e => { e.target.checked ? state.selected.add(d.id) : state.selected.delete(d.id); renderDocs(); };
    $(".doc-main", li).onclick = () => openReader(d.id);
    $("button", li).onclick = async () => {
      try { await api(`/documents/${d.id}`, { method: "DELETE" }); state.selected.delete(d.id); await loadDocs(); } catch (e) { toast(e.message, true); }
    };
    ul.append(li);
  }
  $("#scopeLabel").textContent = state.docs.length ? (state.selected.size ? t("selectedDocs", { n: state.selected.size }) : t("allDocs")) : "";
  fillReaderDocs();
}
const scope = () => (state.selected.size ? [...state.selected] : null);
async function uploadFiles(files) {
  for (const f of files) {
    const row = document.createElement("div"); row.className = "upload-row";
    row.innerHTML = `<span class="spin"></span><span dir="auto">${esc(t("reading", { name: f.name }))}</span>`;
    $("#uploads").append(row);
    try {
      const fd = new FormData(); fd.append("file", f);
      const d = await api("/upload", { method: "POST", body: fd });
      toast(t(d.duplicate ? "duplicate" : "uploaded", { name: d.filename }));
    } catch (e) { toast(`${f.name}: ${e.message}`, true); }
    row.remove();
  }
  await loadDocs();
}

/* ------------------------------------------------------------ AI model */
async function loadModel() { try { state.model = await api("/settings/llm"); renderModel(); } catch { /* ignore */ } }
function renderModel() {
  const m = state.model; if (!m) return;
  $("#modelDot").classList.toggle("on", m.real);
  $("#modelText").textContent = m.real ? `${t("connected")}: ${m.model}` : t("basicMode");
}
const PRESETS = {
  basic: { provider: "extractive" },
  openai: { provider: "openai", base: "https://api.openai.com/v1", model: "gpt-4o-mini" },
  gemini: { provider: "openai", base: "https://generativelanguage.googleapis.com/v1beta/openai", model: "gemini-2.5-flash" },
  groq: { provider: "openai", base: "https://api.groq.com/openai/v1", model: "llama-3.3-70b-versatile" },
  openrouter: { provider: "openai", base: "https://openrouter.ai/api/v1", model: "openai/gpt-4o-mini" },
  claude: { provider: "openai", base: "https://api.anthropic.com/v1", model: "claude-haiku-5-5" },
  ollama: { provider: "ollama", base: "http://localhost:11434", model: "llama3.1" },
  custom: { provider: "openai", base: "", model: "" },
};
const PRESET_LABEL = { basic: "pBasic", openai: "pOpenai", gemini: "pGemini", groq: "pGroq", openrouter: "pOpenrouter", claude: "pClaude", ollama: "pOllama", custom: "pCustom" };
function fillProviders() {
  const sel = $("#sProvider"), cur = sel.value; sel.innerHTML = "";
  for (const k of Object.keys(PRESETS)) sel.append(new Option(t(PRESET_LABEL[k]), k));
  sel.value = cur || "basic"; syncProviderFields(false);
}
function syncProviderFields(fill = true) {
  const p = PRESETS[$("#sProvider").value];
  $("#sFields").classList.toggle("hidden", p.provider === "extractive");
  $("#sKey").parentElement.classList.toggle("hidden", p.provider === "ollama");
  if (fill) { $("#sBase").value = p.base || ""; $("#sModel").value = p.model || ""; }
}
function openSettings() {
  const m = state.model, sel = $("#sProvider");
  if (m) {
    const match = Object.entries(PRESETS).find(([, p]) => p.provider === m.provider && (p.base === (m.provider === "ollama" ? m.ollama_url : m.base_url)));
    sel.value = m.provider === "extractive" ? "basic" : (match ? match[0] : "custom");
    $("#sBase").value = m.provider === "ollama" ? m.ollama_url : m.base_url; $("#sModel").value = m.model;
    $("#sKeyHint").textContent = m.has_key ? t("apiKeyKeep") : t("keyHint");
    const semantic = `${t("searchMode")}: ${m.semantic_search ? t("searchSemantic") : t("searchWords")} (${m.embedding})`;
    $("#sStatus").className = "status-line"; $("#sStatus").textContent = semantic + (m.semantic_search ? "" : ` — ${t("searchTip")}`);
  }
  $("#sKey").value = ""; syncProviderFields(false); $("#settingsDialog").showModal();
}
async function saveSettings(e) {
  e.preventDefault();
  const p = PRESETS[$("#sProvider").value], btn = $("#sSave"), st = $("#sStatus");
  const body = { provider: p.provider, model: $("#sModel").value.trim() || null, api_key: $("#sKey").value.trim() || null };
  if (p.provider === "ollama") body.ollama_url = $("#sBase").value.trim() || null; else if (p.provider === "openai") body.base_url = $("#sBase").value.trim() || null;
  btn.disabled = true; st.className = "status-line"; st.textContent = t("saving");
  try {
    state.model = await post("/settings/llm", body); renderModel();
    st.className = "status-line ok"; st.textContent = "✓ " + (state.model.real ? t("connected") : t("basicMode"));
    setTimeout(() => $("#settingsDialog").close(), 700);
  } catch (err) { st.className = "status-line err"; st.textContent = err.message; }
  btn.disabled = false;
}

/* ------------------------------------------------------------ speech (read aloud) */
const synth = window.speechSynthesis;
const Speech = {
  session: 0, sentences: [], idx: 0, playing: false, paused: false, voices: [], onSentence: null, onEnd: null,
  loadVoices() { this.voices = synth ? synth.getVoices() : []; fillVoices(); },
  langFor(text) {
    if (hasArabic(text)) return state.lang === "sd" ? "sd" : "ur";
    return "en";
  },
  pick(lang) {
    const want = $("#voiceSel").value;
    if (want && want !== "auto") { const v = this.voices.find(x => x.voiceURI === want); if (v) return v; }
    const order = { en: ["en-US", "en-GB", "en"], ur: ["ur-PK", "ur"], sd: ["sd", "ur-PK", "ur", "ar"] }[lang];
    for (const code of order) {
      const v = this.voices.find(x => x.lang.toLowerCase() === code.toLowerCase()) || this.voices.find(x => x.lang.toLowerCase().startsWith(code.toLowerCase()));
      if (v) return v;
    }
    return null;
  },
  split(text) {
    const parts = text.replace(/\s+/g, " ").match(/[^.!?۔؟\n]+[.!?۔؟]*/g) || [text];
    const out = [];
    for (let p of parts) {
      p = p.trim(); if (!p) continue;
      while (p.length > 220) { let cut = p.lastIndexOf(" ", 200); if (cut < 80) cut = 200; out.push(p.slice(0, cut)); p = p.slice(cut).trim(); }
      if (p) out.push(p);
    }
    return out;
  },
  start(sentences, from = 0, hooks = {}) {
    if (!synth) { toast(t("noSpeech"), true); return; }
    this.stop(true);
    this.sentences = sentences; this.idx = from; this.onSentence = hooks.onSentence || null; this.onEnd = hooks.onEnd || null;
    this.playing = true; this.paused = false; this.next(++this.session); refreshPlayers();
  },
  next(session) {
    if (session !== this.session || !this.playing) return;
    if (this.idx >= this.sentences.length) { const cb = this.onEnd; this.playing = false; refreshPlayers(); if (cb) cb(); return; }
    const text = this.sentences[this.idx], lang = this.langFor(text), voice = this.pick(lang);
    const u = new SpeechSynthesisUtterance(text);
    u.lang = voice ? voice.lang : ({ en: "en-US", ur: "ur-PK", sd: "sd-PK" })[lang];
    if (voice) u.voice = voice;
    u.rate = parseFloat($("#rate").value) || 1;
    showVoiceNotice(lang, voice);
    if (this.onSentence) this.onSentence(this.idx);
    const advance = () => { if (session === this.session) { this.idx++; this.next(session); } };
    u.onend = advance; u.onerror = ev => { if (ev.error !== "canceled" && ev.error !== "interrupted") advance(); };
    synth.speak(u);
  },
  pause() { if (synth && this.playing) { synth.pause(); this.paused = true; refreshPlayers(); } },
  resume() { if (synth && this.paused) { synth.resume(); this.paused = false; refreshPlayers(); } },
  stop(silent) { this.session++; this.playing = false; this.paused = false; if (synth) synth.cancel(); if (!silent) { if (this.onSentence) this.onSentence(-1); refreshPlayers(); } },
  jump(delta) { if (!this.sentences.length) return; const to = Math.max(0, Math.min(this.sentences.length - 1, this.idx + delta)); this.start(this.sentences, to, { onSentence: this.onSentence, onEnd: this.onEnd }); },
};
function showVoiceNotice(lang, voice) {
  const n = $("#voiceNotice"); const missing = !voice || (lang !== "en" && !voice.lang.toLowerCase().startsWith(lang === "sd" ? "sd" : "ur") && lang === "ur");
  const sindhiFallback = lang === "sd" && voice && !voice.lang.toLowerCase().startsWith("sd");
  n.textContent = t("noVoice"); n.classList.toggle("hidden", !(missing || sindhiFallback));
}
function fillVoices() {
  const sel = $("#voiceSel"), cur = sel.value; sel.innerHTML = ""; sel.append(new Option(t("autoVoice"), "auto"));
  const pref = { en: "en", ur: "ur", sd: "sd" }[state.lang];
  const vs = [...Speech.voices].sort((a, b) => (b.lang.startsWith(pref) - a.lang.startsWith(pref)) || a.name.localeCompare(b.name));
  for (const v of vs) sel.append(new Option(`${v.name} (${v.lang})`, v.voiceURI));
  sel.value = [...sel.options].some(o => o.value === cur) ? cur : "auto";
}
function refreshPlayers() {
  const label = Speech.playing && !Speech.paused ? "⏸ " + t("pause") : (Speech.paused ? "▶ " + t("resume") : "▶ " + t("play"));
  $("#rPlay").textContent = label;
  $$("[data-speak]").forEach(b => { const on = b.dataset.speak === String(speakOwner); b.classList.toggle("on", on && Speech.playing); b.textContent = on && Speech.playing ? "⏹ " + t("stopSpeech") : "🔊 " + t("listen"); });
  const lo = $("#outListen"); if (lo) lo.textContent = (speakOwner === "out" && Speech.playing) ? "⏹ " + t("stopSpeech") : "🔊 " + t("listen");
}
let speakOwner = null;
function toggleSpeak(owner, text) {
  if (speakOwner === owner && Speech.playing) { Speech.stop(); speakOwner = null; refreshPlayers(); return; }
  speakOwner = owner;
  Speech.start(Speech.split(speakable(text)), 0, { onEnd: () => { speakOwner = null; refreshPlayers(); } });
  refreshPlayers();
}

/* voice input */
let recog = null;
function toggleMic() {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  if (!SR) { toast(t("micUnsupported"), true); return; }
  if (recog) { recog.stop(); return; }
  recog = new SR(); recog.lang = I18N[state.lang].speech; recog.interimResults = true; recog.maxAlternatives = 1;
  const box = $("#question"); $("#micBtn").classList.add("mic-on"); toast(t("listening"));
  recog.onresult = e => { box.value = [...e.results].map(r => r[0].transcript).join(" "); autosize(); };
  recog.onerror = () => toast(t("micError"), true);
  recog.onend = () => { recog = null; $("#micBtn").classList.remove("mic-on"); if (box.value.trim() && state.autoSend) { state.autoSend = false; $("#composer").requestSubmit(); } };
  state.autoSend = true; recog.start();
}

/* ------------------------------------------------------------ chat */
function renderSuggestions() {
  const box = $("#suggestions"); if (!box) return; box.innerHTML = "";
  for (const k of ["sugSummary", "sugKey", "sugQuiz", "sugNotes"]) {
    const b = document.createElement("button"); b.className = "chip"; b.type = "button"; b.textContent = t(k);
    b.onclick = () => { $("#question").value = t(k); $("#composer").requestSubmit(); }; box.append(b);
  }
}
const INTENTS = [
  ["notes", /\bnotes?\b|نوٹس|نوٽس/i], ["flashcards", /\bflash\s?cards?\b|فلیش|فليش/i],
  ["quiz", /\b(quiz|mcqs?|multiple[\s-]choice)\b|کوئز|ڪوئز/i], ["assignment", /\bassignment\b|\bhomework\b|اسائنمنٹ|اسائنمينٽ/i],
  ["mid_exam", /\bmid[\s-]?(term)?\b.*\b(exam|paper|test)\b|مڈ\s?ٹرم|مڊ\s?ٽرم/i], ["final_exam", /\bfinal\b.*\b(exam|paper|test)\b|فائنل/i],
  ["summary", /\b(summari[sz]e|summary|overview|tl;?dr)\b|خلاصہ|خلاصو/i],
  ["explain", /^\s*(explain|teach me|tell me about|describe)\b|سمجھائ|سمجهاي|وضاحت/i],
];
function detectIntent(q) {
  for (const [task, re] of INTENTS) if (re.test(q)) {
    const req = { task, instructions: q.slice(0, 600) };
    const pg = q.match(/\bpages?\s*(\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+)*)/i); if (pg) req.pages = pg[1];
    const n = q.match(/(\d+)\s*(questions?|mcqs?|cards?|سوال)/i); if (n) req.count = Math.min(50, +n[1]);
    const mk = q.match(/(\d+)\s*(marks?|نمبر)/i); if (mk) req.total_marks = Math.max(5, Math.min(200, +mk[1]));
    if (task === "explain") req.topic = q.replace(/^\s*(explain|teach me|tell me about|describe)\s*(to me)?\s*/i, "").slice(0, 300) || null;
    else { const tp = q.match(/\b(?:on|about|regarding|covering)\s+(.{3,})$/i); if (tp && !/exam|paper|quiz|test|assignment/i.test(tp[1])) req.topic = tp[1].slice(0, 300); }
    return req;
  }
  return null;
}
function addMsg(role) {
  $("#welcome")?.remove();
  const wrap = document.createElement("div"); wrap.className = "msg " + role;
  wrap.innerHTML = `<div class="bubble" dir="auto"></div><div class="msg-actions"></div>`;
  $("#messages").append(wrap); wrap.scrollIntoView({ block: "end", behavior: "smooth" }); return wrap;
}
const scrollEnd = () => { const m = $("#messages"); m.scrollTop = m.scrollHeight; };
function autosize() { const q = $("#question"); q.style.height = "auto"; q.style.height = Math.min(q.scrollHeight, 140) + "px"; }
function setBusy(b) {
  state.busy = b; const btn = $("#sendBtn"); btn.textContent = b ? t("stop") : t("send");
  btn.type = b ? "button" : "submit"; btn.onclick = b ? () => state.abort?.abort() : null;
}
async function ask(e) {
  e.preventDefault();
  if (state.busy) return;
  const q = $("#question").value.trim(); if (!q) return;
  if (!state.docs.length) { toast(t("uploadFirst"), true); return; }
  $("#question").value = ""; autosize();
  addMsg("user").querySelector(".bubble").textContent = q;
  const bot = addMsg("bot"), bubble = $(".bubble", bot);
  bubble.innerHTML = `<span class="dots"><span></span><span></span><span></span></span>`;
  state.abort = new AbortController(); setBusy(true);
  const intent = detectIntent(q);
  let text = "";
  try {
    if (intent) {
      let started = false;
      await stream("/study/stream", { ...intent, language: state.lang, document_ids: scope() }, {
        status: s => { bubble.textContent = t("partN", { i: s.step, n: s.total }); },
        token: d => { if (!started) { started = true; bubble.textContent = ""; } text += d.text; bubble.textContent = text; scrollEnd(); },
        final: d => { text = d.markdown; renderBotAnswer(bot, text, [], true, d); },
        error: d => { throw new Error(d.message); },
      }, state.abort.signal);
    } else {
      let started = false, sources = [];
      await stream("/query/stream", { question: q, language: state.lang, document_ids: scope(), history: state.history.slice(-3) }, {
        sources: d => { sources = d.sources; },
        token: d => { if (!started) { started = true; bubble.textContent = ""; } text += d.text; bubble.textContent = text; scrollEnd(); },
        final: d => { text = d.answer; state.history.push({ question: q, answer: d.answer }); renderBotAnswer(bot, d.answer, d.sources, d.found, d); },
        error: d => { throw new Error(d.message); },
      }, state.abort.signal);
    }
    if ($("#autoRead").checked && text) toggleSpeak("auto", text);
  } catch (err) {
    if (err.name === "AbortError") { bubble.textContent = text || "…"; }
    else { bubble.textContent = err.message; bubble.style.color = "var(--danger)"; }
  }
  setBusy(false); state.abort = null; scrollEnd();
}
function renderBotAnswer(bot, text, sources, found, meta) {
  const bubble = $(".bubble", bot), actions = $(".msg-actions", bot);
  const isStudy = meta && meta.task;
  let body = text.split(MARKER)[0];
  bubble.innerHTML = isStudy ? md(text.replace(MARKER, "\n---\n")) : withCitations(md(body));
  bot._sources = sources;
  if (!isStudy && sources.length) {
    const cited = sources.filter(s => s.cited);
    const row = document.createElement("div"); row.className = "srcrow";
    for (const s of (cited.length ? cited : sources.slice(0, 3))) {
      const b = document.createElement("button"); b.className = "srcpill"; b.type = "button"; b.dir = "auto";
      b.textContent = `[${s.number}] ${s.filename} · ${t("page")} ${s.page}`; b.onclick = () => openDrawer(sources, s.number); row.append(b);
    }
    bubble.append(row);
    $$(".cite", bubble).forEach(c => c.onclick = () => openDrawer(sources, +c.dataset.n));
  }
  if (!isStudy && !found && state.model && !state.model.real) { const h = document.createElement("div"); h.className = "hint"; h.textContent = t("notFoundHint"); bubble.append(h); }
  actions.innerHTML = "";
  const mk = (label, fn, attrs = {}) => { const b = document.createElement("button"); b.className = "act"; b.type = "button"; b.textContent = label; Object.assign(b.dataset, attrs); b.onclick = fn; actions.append(b); return b; };
  const id = "m" + Math.random().toString(36).slice(2);
  mk("🔊 " + t("listen"), () => toggleSpeak(id, text), { speak: id });
  mk("⧉ " + t("copy"), async () => { try { await navigator.clipboard.writeText(text); toast(t("copied")); } catch { /* ignore */ } });
  if (meta && meta.query_id) {
    const fb = async helpful => { try { await post("/feedback", { query_id: meta.query_id, helpful }); toast(t("thanks")); } catch (e) { toast(e.message, true); } };
    mk("👍", () => fb(true)).title = t("helpful"); mk("👎", () => fb(false)).title = t("notHelpful");
  }
  scrollEnd();
}
function openDrawer(sources, focus) {
  const body = $("#drawerBody"); body.innerHTML = "";
  const common = new Set("the and for are was were what which who how does with that this from have has when where why much many can you your about into than then they them their there here".split(" "));
  const words = [...new Set((state.history.at(-1)?.question || "").toLowerCase().match(/[\p{L}\p{N}]{3,}/gu) || [])].filter(w => !common.has(w));
  const re = words.length ? new RegExp("(" + words.map(w => w.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")).join("|") + ")", "giu") : null;
  for (const s of sources) {
    const d = document.createElement("div"); d.className = "src" + (s.number === focus ? " focus" : ""); d.id = "src" + s.number;
    const txt = esc(s.text); d.innerHTML = `<div class="src-h"><span class="cite">${s.number}</span><span dir="auto">${esc(s.filename)}</span> · ${esc(t("page"))} ${s.page}</div><div dir="auto">${re ? txt.replace(re, "<mark>$1</mark>") : txt}</div>`;
    body.append(d);
  }
  $("#drawer").classList.remove("hidden"); $("#src" + focus)?.scrollIntoView({ block: "center" });
}

/* ------------------------------------------------------------ study tools */
const TOOLS = [["summary", "📝"], ["explain", "💡"], ["notes", "📒"], ["quiz", "❓"], ["flashcards", "🃏"], ["assignment", "📎"], ["mid_exam", "📄"], ["final_exam", "🎓"]];
function renderTools() {
  const box = $("#tools"); box.innerHTML = "";
  for (const [k, icon] of TOOLS) {
    const b = document.createElement("button"); b.type = "button"; b.className = "tool" + (state.tool === k ? " on" : "");
    b.innerHTML = `<span class="ti">${icon}</span><b>${esc(t("t_" + k))}</b><span>${esc(t("d_" + k))}</span>`;
    b.onclick = () => selectTool(k); box.append(b);
  }
  if (state.tool) syncOptions();
}
function selectTool(k) {
  state.tool = k; $("#options").classList.remove("hidden");
  if (k === "quiz") $("#optCount").value = 10; if (k === "flashcards") $("#optCount").value = 15;
  $("#optMarks").value = { assignment: 20, mid_exam: 30, final_exam: 60 }[k] || 30;
  renderTools();
}
function syncOptions() { $$("#options [data-for]").forEach(f => f.classList.toggle("hidden", !f.dataset.for.split(" ").includes(state.tool))); }
async function generate(e) {
  e.preventDefault();
  if (!state.docs.length) { toast(t("pickDocFirst"), true); return; }
  const req = { task: state.tool, language: state.lang, document_ids: scope(), topic: $("#optTopic").value.trim() || null, pages: $("#optPages").value.trim() || null,
    instructions: $("#optExtra").value.trim() || null, difficulty: $("#optDifficulty").value, length: $("#optLength").value };
  if (["quiz", "flashcards"].includes(state.tool)) req.count = +$("#optCount").value || null;
  if (["assignment", "mid_exam", "final_exam"].includes(state.tool)) req.total_marks = +$("#optMarks").value || null;
  const btn = $("#genBtn"); btn.disabled = true; btn.textContent = t("generating");
  state.md = ""; state.practice = false; state.showAnswers = false; $("#outputMeta").textContent = "";
  $("#output").innerHTML = `<p class="muted empty"><span class="spin" style="display:inline-block"></span></p>`; $("#outputBar").classList.remove("hidden");
  let live = "";
  try {
    await stream("/study/stream", req, {
      meta: m => { state.sources = m.sources; $("#outputMeta").textContent = t("sourcesUsed") + ": " + m.sources.map(s => `${s.filename} (${t("page")} ${compactPages(s.pages)})`).join(", "); },
      status: s => { $("#output").innerHTML = `<p class="muted empty">${esc(t("partN", { i: s.step, n: s.total }))}</p>`; },
      token: d => { live += d.text; $("#output").innerHTML = md(live.split(MARKER)[0]); },
      final: d => { state.md = d.markdown; state.tool = d.task; renderOutput(); if (d.sampled) $("#outputMeta").textContent += " · " + t("sampledNote"); },
      error: d => { throw new Error(d.message); },
    });
  } catch (err) { $("#output").innerHTML = `<p style="color:var(--danger)">${esc(err.message)}</p>`; }
  btn.disabled = false; btn.textContent = t("generate"); updateOutputBar();
}
function compactPages(p) { if (p.length > 6) return `${p[0]}–${p[p.length - 1]}`; return p.join(", "); }
function parseQuiz(markdown) {
  const [qPart, aPart = ""] = markdown.split(MARKER);
  const answers = {}; for (const m of aPart.matchAll(/^\s*(\d+)[.)]\s*\**\(?([A-Da-d])\b[^\n]*$/gm)) answers[+m[1]] = { letter: m[2].toUpperCase(), line: m[0].replace(/^\s*\d+[.)]\s*/, "") };
  const qs = []; let cur = null;
  for (const line of qPart.split("\n")) {
    const q = line.match(/^\s*(\d+)[.)]\s+(.*)$/), o = line.match(/^\s*[-*•]?\s*([A-Da-d])[).]\s+(.*)$/);
    if (q && !o) { cur = { n: +q[1], text: q[2], opts: [] }; qs.push(cur); } else if (o && cur) cur.opts.push({ l: o[1].toUpperCase(), text: o[2] });
  }
  const ok = qs.filter(q => q.opts.length >= 2 && answers[q.n]);
  return ok.length >= 2 ? ok.map(q => ({ ...q, ...answers[q.n] })) : null;
}
function renderOutput() {
  const out = $("#output"), [paper, answers = ""] = state.md.split(MARKER);
  const quiz = state.tool === "quiz" ? parseQuiz(state.md) : null;
  if (state.tool === "flashcards") { const cards = flashcards(state.md); if (cards) { out.innerHTML = cards; return; } }
  if (quiz && state.practice) { out.innerHTML = practiceHtml(quiz); return; }
  let html = md(paper);
  if (answers.trim() && state.showAnswers) html += "<hr>" + md(answers);
  out.innerHTML = html;
}
function flashcards(markdown) {
  const blocks = markdown.split(/\n\s*\n/).map(b => b.split("\n").filter(l => /^\*\*[^*]+:\*\*/.test(l.trim())));
  const pairs = blocks.filter(b => b.length >= 2); if (pairs.length < 2) return null;
  const head = markdown.match(/^##\s+(.*)$/m);
  const strip = l => l.trim().replace(/^\*\*[^*]+:\*\*\s*/, "");
  return (head ? `<h2>${esc(head[1])}</h2>` : "") + `<div class="cards">` + pairs.map(p => `<div class="card"><div>${inline(strip(p[0]))}</div><div class="a">${inline(strip(p[1]))}</div><div class="r">${esc(t("reveal"))}</div></div>`).join("") + "</div>";
}
function practiceHtml(qs) {
  return `<div class="scorebox" id="score">${esc(t("score", { s: 0, n: qs.length }))}</div>` + qs.map((q, i) => `<div class="mcq" data-i="${i}"><div><strong>${q.n}.</strong> ${inline(q.text)}</div>` +
    q.opts.map(o => `<button type="button" class="opt" data-l="${o.l}"><b>${o.l})</b> ${inline(o.text)}</button>`).join("") + `<div class="why hidden"></div></div>`).join("");
}
function updateOutputBar() {
  const has = !!state.md; $("#outputBar").classList.toggle("hidden", !has);
  $("#outCopy").textContent = "⧉ " + t("copy"); $("#outDocx").textContent = "⬇ " + t("download"); $("#outPrint").textContent = "🖶 " + t("printPdf");
  const hasAns = state.md.includes(MARKER), quiz = has && state.tool === "quiz" && parseQuiz(state.md);
  $("#outAnswers").classList.toggle("hidden", !hasAns || (state.practice && !!quiz) || state.tool === "flashcards");
  $("#outAnswers").textContent = state.showAnswers ? t("hideAnswers") : t("showAnswers");
  $("#outPractice").classList.toggle("hidden", !quiz); $("#outPractice").textContent = state.practice ? t("paperView") : "🎯 " + t("practice");
  refreshPlayers();
}

/* ------------------------------------------------------------ reader */
function fillReaderDocs() {
  const sel = $("#readerDoc"), cur = state.readerDoc || sel.value; sel.innerHTML = "";
  sel.append(new Option(t("chooseDoc"), ""));
  for (const d of state.docs) sel.append(new Option(d.filename, d.id));
  sel.value = state.docs.some(d => d.id === cur) ? cur : "";
}
function renderReaderControls() { refreshPlayers(); $("#rateOut").textContent = $("#rate").value + "×"; fillVoices(); renderReaderPage(); }
async function openReader(id) { switchTab("reader"); $("#readerDoc").value = id; await loadReader(id); }
async function loadReader(id) {
  Speech.stop(); state.readerDoc = id || null;
  if (!id) { state.readerPages = []; renderReaderPage(); return; }
  try { const d = await api(`/documents/${id}/text`); state.readerPages = d.pages; state.readerPage = 0; renderReaderPage(); } catch (e) { toast(e.message, true); }
}
function renderReaderPage() {
  const box = $("#readerText"), pages = state.readerPages;
  $("#pageLabel").textContent = pages.length ? t("pageOf", { p: pages[state.readerPage].page, n: pages.length }) : "";
  box.innerHTML = ""; if (!pages.length) return;
  const sents = Speech.split(pages[state.readerPage].text);
  box._sents = sents;
  box.innerHTML = sents.map((s, i) => `<span class="sent" data-i="${i}">${esc(s)}</span> `).join("");
  $$(".sent", box).forEach(sp => sp.onclick = () => readerPlay(+sp.dataset.i));
}
function readerPlay(from = 0) {
  const box = $("#readerText"); if (!box._sents) return; speakOwner = "reader";
  Speech.start(box._sents, from, {
    onSentence: i => { $$(".sent.now", box).forEach(e => e.classList.remove("now")); const el = $(`.sent[data-i="${i}"]`, box); if (el) { el.classList.add("now"); el.scrollIntoView({ block: "center", behavior: "smooth" }); } },
    onEnd: () => { if (state.readerPage < state.readerPages.length - 1) { state.readerPage++; renderReaderPage(); readerPlay(0); } else speakOwner = null; },
  });
}

/* ------------------------------------------------------------ wiring */
function switchTab(name) {
  state.tab = name; $$(".tab").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  $$(".view").forEach(v => v.classList.toggle("hidden", v.id !== "view-" + name));
  if (name === "reader") fillReaderDocs();
}
function init() {
  applyTheme(); applyLang(); loadDocs(); loadModel();
  $$(".tab").forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  $$("#langSeg button").forEach(b => b.onclick = () => { state.lang = b.dataset.lang; store.set("am.lang", state.lang); applyLang(); });
  $("#themeBtn").onclick = () => { const dark = document.documentElement.dataset.theme === "dark"; state.theme = dark ? "light" : "dark"; store.set("am.theme", state.theme); applyTheme(); };
  const dz = $("#dropzone");
  $("#fileInput").onchange = e => { uploadFiles([...e.target.files]); e.target.value = ""; };
  ["dragenter", "dragover"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.add("over"); }));
  ["dragleave", "drop"].forEach(ev => dz.addEventListener(ev, e => { e.preventDefault(); dz.classList.remove("over"); }));
  dz.addEventListener("drop", e => uploadFiles([...e.dataTransfer.files]));
  $("#composer").onsubmit = ask;
  $("#question").addEventListener("input", autosize);
  $("#question").addEventListener("keydown", e => { if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); $("#composer").requestSubmit(); } });
  $("#micBtn").onclick = toggleMic;
  $("#autoRead").checked = store.get("am.autoread", "") === "1"; $("#autoRead").onchange = e => store.set("am.autoread", e.target.checked ? "1" : "0");
  $("#options").onsubmit = generate;
  $("#outListen").onclick = () => toggleSpeak("out", state.md.split(MARKER)[0] + (state.showAnswers ? " " + (state.md.split(MARKER)[1] || "") : ""));
  $("#outCopy").onclick = async () => { try { await navigator.clipboard.writeText(state.md.replace(MARKER, "\n---\n")); toast(t("copied")); } catch { /* ignore */ } };
  $("#outDocx").onclick = async () => {
    try {
      const res = await fetch("/export/docx", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ markdown: state.md, title: t("t_" + state.tool), language: state.lang }) });
      if (!res.ok) throw new Error(errText(await res.json().catch(() => null), res.status));
      const url = URL.createObjectURL(await res.blob()), a = document.createElement("a"); a.href = url; a.download = `automind-${state.tool}.docx`; a.click(); URL.revokeObjectURL(url);
    } catch (e) { toast(e.message, true); }
  };
  $("#outPrint").onclick = () => window.print();
  $("#outAnswers").onclick = () => { state.showAnswers = !state.showAnswers; renderOutput(); updateOutputBar(); };
  $("#outPractice").onclick = () => { state.practice = !state.practice; renderOutput(); updateOutputBar(); };
  $("#output").addEventListener("click", e => {
    const card = e.target.closest(".card"); if (card) card.classList.toggle("open");
    const opt = e.target.closest(".opt"); if (!opt) return;
    const box = opt.closest(".mcq"); if (box.dataset.done) return; box.dataset.done = "1";
    const q = parseQuiz(state.md)[+box.dataset.i], right = opt.dataset.l === q.letter;
    $$(".opt", box).forEach(o => { if (o.dataset.l === q.letter) o.classList.add("right"); });
    if (!right) opt.classList.add("bad"); else box.dataset.ok = "1";
    const why = $(".why", box); why.classList.remove("hidden"); why.textContent = (right ? "✓ " + t("correct") : "✗ " + t("wrong")) + " — " + q.line.replace(/\*\*/g, "");
    const total = $$(".mcq").length, got = $$(".mcq[data-ok]").length; $("#score").textContent = t("score", { s: got, n: total });
  });
  $("#readerDoc").onchange = e => loadReader(e.target.value);
  $("#rPlay").onclick = () => { if (!state.readerPages.length) return; if (Speech.paused) Speech.resume(); else if (Speech.playing && speakOwner === "reader") Speech.pause(); else readerPlay(0); };
  $("#rStop").onclick = () => { Speech.stop(); speakOwner = null; refreshPlayers(); };
  $("#rPrev").onclick = () => Speech.jump(-1); $("#rNext").onclick = () => Speech.jump(1);
  $("#pPrev").onclick = () => { if (state.readerPage > 0) { Speech.stop(); state.readerPage--; renderReaderPage(); } };
  $("#pNext").onclick = () => { if (state.readerPage < state.readerPages.length - 1) { Speech.stop(); state.readerPage++; renderReaderPage(); } };
  $("#rate").oninput = () => { $("#rateOut").textContent = $("#rate").value + "×"; };
  $("#sProvider").onchange = () => syncProviderFields(true);
  $("#modelChip").onclick = $("#settingsBtn").onclick = openSettings;
  $("#settingsClose").onclick = () => $("#settingsDialog").close(); $("#settingsForm").onsubmit = saveSettings;
  $("#drawerClose").onclick = () => $("#drawer").classList.add("hidden");
  const side = $("#sidebar"), back = $("#backdrop");
  const openSide = o => { side.classList.toggle("open", o); back.classList.toggle("hidden", !o); };
  $("#menuBtn").onclick = () => openSide(true); $("#closeSide").onclick = back.onclick = () => openSide(false);
  if (synth) { Speech.loadVoices(); synth.onvoiceschanged = () => Speech.loadVoices(); }
  window.addEventListener("beforeunload", () => synth && synth.cancel());
  refreshPlayers();
}
init();
})();
