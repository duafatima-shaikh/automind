"""AutoMind, Streamlit version.

One process, no separate API server, so it runs on Streamlit Community Cloud.
Run locally:   streamlit run streamlit_app.py

It talks straight to the same `automind` package that the FastAPI version uses
(parsing, chunking, hybrid search, reranking, citation checking, study tools).
"""
from __future__ import annotations

import html
import json
import os
import re
import sys
import tempfile
from pathlib import Path

import streamlit as st
import streamlit.components.v1 as components

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

# Streamlit Cloud has about 1 GB of memory, so use the small offline encoder unless the owner
# installs sentence-transformers and asks for it (AUTOMIND_EMBEDDING_BACKEND in Secrets).
os.environ.setdefault("AUTOMIND_EMBEDDING_BACKEND", "hash")

from ui_i18n import I18N  # noqa: E402

MARKER = "---ANSWERS---"
SAMPLE_DIR = ROOT / "src" / "automind" / "evaluation" / "datasets" / "sample_docs"
LANGS = {"en": "English", "ur": "اردو", "sd": "سنڌي"}
TASKS = ["summary", "explain", "notes", "quiz", "flashcards", "assignment", "mid_exam",
         "final_exam"]
TASK_ICONS = {"summary": "📝", "explain": "💡", "notes": "📒", "quiz": "❓", "flashcards": "🃏",
              "assignment": "📄", "mid_exam": "🎓", "final_exam": "🏆"}
PRESETS = {
    "basic": {"provider": "extractive"},
    "openai": {"provider": "openai", "base": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
    "gemini": {"provider": "openai",
               "base": "https://generativelanguage.googleapis.com/v1beta/openai",
               "model": "gemini-2.5-flash"},
    "groq": {"provider": "openai", "base": "https://api.groq.com/openai/v1",
             "model": "llama-3.3-70b-versatile"},
    "openrouter": {"provider": "openai", "base": "https://openrouter.ai/api/v1",
                   "model": "openai/gpt-4o-mini"},
    "claude": {"provider": "openai", "base": "https://api.anthropic.com/v1",
               "model": "claude-haiku-5-5"},
    "ollama": {"provider": "ollama", "base": "http://localhost:11434", "model": "llama3.1"},
    "custom": {"provider": "openai", "base": "", "model": ""},
}
PRESET_LABEL = {"basic": "pBasic", "openai": "pOpenai", "gemini": "pGemini", "groq": "pGroq",
                "openrouter": "pOpenrouter", "claude": "pClaude", "ollama": "pOllama",
                "custom": "pCustom"}
STOPWORDS = {
    "the", "and", "for", "are", "was", "what", "which", "how", "does", "with", "that", "this",
    "from", "have", "has", "who", "why", "when", "where", "much", "many", "can", "you", "your",
}
INTENTS = [
    ("notes", r"\bnotes?\b|نوٹس|نوٽس"),
    ("flashcards", r"\bflash\s?cards?\b|فلیش|فليش"),
    ("quiz", r"\b(quiz|mcqs?|multiple[\s-]choice)\b|کوئز|ڪوئز"),
    ("assignment", r"\bassignment\b|\bhomework\b|اسائنمنٹ|اسائنمينٽ"),
    ("mid_exam", r"\bmid[\s-]?(term)?\b.*\b(exam|paper|test)\b|مڈ\s?ٹرم|مڊ\s?ٽرم"),
    ("final_exam", r"\bfinal\b.*\b(exam|paper|test)\b|فائنل"),
    ("summary", r"\b(summari[sz]e|summary|overview|tl;?dr)\b|خلاصہ|خلاصو"),
    ("explain", r"^\s*(explain|teach me|tell me about|describe)\b|سمجھائ|سمجهاي|وضاحت"),
]

st.set_page_config(page_title="AutoMind", page_icon="🧠", layout="wide")


# ----------------------------------------------------------------------------- text and style
def lang() -> str:
    return st.session_state.get("lang", "en")


def t(key: str, **values) -> str:
    text = I18N[lang()].get(key) or I18N["en"].get(key, key)
    for name, value in values.items():
        text = text.replace("{" + name + "}", str(value))
    return text


def inject_css() -> None:
    rtl = lang() in ("ur", "sd")
    direction = (
        """
        .stMarkdown, .stChatMessage, .stAlert, label, .stCaption, .stRadio, .stCheckbox,
        .stTextInput, .stTextArea, .stSelectbox, .streamlit-expanderHeader, summary {
            direction: rtl; text-align: right;
        }
        """ if rtl else ""
    )
    st.markdown(
        f"""
        <style>
        @import url('https://fonts.googleapis.com/css2?family=Noto+Nastaliq+Urdu&family=Noto+Naskh+Arabic&display=swap');
        {direction}
        .am-rtl {{ font-family: 'Noto Naskh Arabic', serif; line-height: 2; }}
        .am-src {{ font-size: 0.92rem; line-height: 1.6; }}
        .am-src mark {{ background: #ffe58a; padding: 0 2px; border-radius: 3px; }}
        .block-container {{ padding-top: 2rem; }}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ----------------------------------------------------------------------------- services
def apply_secret_defaults(svc) -> None:
    """The app owner can pre-connect an AI model in Streamlit Secrets (see README)."""
    try:
        secrets = dict(st.secrets)
    except Exception:  # noqa: BLE001  (no secrets file)
        return
    key = secrets.get("LLM_API_KEY")
    provider = secrets.get("LLM_PROVIDER", "openai")
    if not key and provider != "ollama":
        return
    try:
        svc.configure_llm({
            "provider": provider, "model": secrets.get("LLM_MODEL"),
            "api_key": key, "base_url": secrets.get("LLM_BASE_URL"),
        }, test=False)
    except Exception as error:  # noqa: BLE001
        st.session_state.secret_error = str(error)


def get_services():
    """One private library per browser session, so visitors never see each other's files."""
    if "svc" not in st.session_state:
        from automind.config import Settings
        from automind.services import Services

        folder = Path(tempfile.mkdtemp(prefix="automind_"))
        svc = Services(Settings(data_dir=folder, _env_file=None))
        apply_secret_defaults(svc)
        st.session_state.svc = svc
    return st.session_state.svc


def ingest(svc, name: str, data: bytes):
    from automind.ingestion.ocr import OCRUnavailable
    from automind.ingestion.parsers import EmptyDocumentError, UnsupportedFileType

    try:
        return svc.ingestion.ingest(name, data), None
    except UnsupportedFileType as error:
        return None, str(error)
    except OCRUnavailable as error:
        return None, str(error)
    except EmptyDocumentError as error:
        return None, str(error)
    except Exception as error:  # noqa: BLE001
        return None, f"Could not read this file: {error}"


# ----------------------------------------------------------------------------- helpers
def highlight(text: str, question: str) -> str:
    safe = html.escape(text)
    words = {w for w in re.findall(r"\w+", question.lower()) if len(w) > 2 and w not in STOPWORDS}
    if not words:
        return safe
    pattern = re.compile(
        r"(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")",
        re.IGNORECASE)
    return pattern.sub(r"<mark>\1</mark>", safe)


def detect_intent(question: str) -> dict | None:
    for task, pattern in INTENTS:
        if not re.search(pattern, question, re.IGNORECASE):
            continue
        req: dict = {"task": task, "instructions": question[:600]}
        pages = re.search(r"\bpages?\s*(\d+(?:\s*[-–]\s*\d+)?(?:\s*,\s*\d+)*)", question, re.I)
        if pages:
            req["pages"] = pages.group(1)
        count = re.search(r"(\d+)\s*(questions?|mcqs?|cards?|سوال)", question, re.I)
        if count:
            req["count"] = min(50, int(count.group(1)))
        marks = re.search(r"(\d+)\s*(marks?|نمبر)", question, re.I)
        if marks:
            req["total_marks"] = max(5, min(200, int(marks.group(1))))
        if task == "explain":
            topic = re.sub(r"^\s*(explain|teach me|tell me about|describe)\s*(to me)?\s*", "",
                           question, flags=re.I)[:300]
            req["topic"] = topic or None
        else:
            found = re.search(r"\b(?:on|about|regarding|covering)\s+(.{3,})$", question, re.I)
            if found and not re.search(r"exam|paper|quiz|test|assignment", found.group(1), re.I):
                req["topic"] = found.group(1)[:300]
        return req
    return None


def parse_quiz(markdown: str):
    paper, _, key = markdown.partition(MARKER)
    answers = {}
    for m in re.finditer(r"^\s*(\d+)[.)]\s*\**\(?([A-Da-d])\b[^\n]*$", key, re.M):
        answers[int(m.group(1))] = {
            "letter": m.group(2).upper(), "line": re.sub(r"^\s*\d+[.)]\s*", "", m.group(0))}
    questions, current = [], None
    for line in paper.split("\n"):
        q = re.match(r"^\s*(\d+)[.)]\s+(.*)$", line)
        o = re.match(r"^\s*[-*•]?\s*([A-Da-d])[).]\s+(.*)$", line)
        if q and not o:
            current = {"n": int(q.group(1)), "text": q.group(2), "opts": []}
            questions.append(current)
        elif o and current:
            current["opts"].append({"l": o.group(1).upper(), "text": o.group(2)})
    good = [q for q in questions if len(q["opts"]) >= 2 and q["n"] in answers]
    return [{**q, **answers[q["n"]]} for q in good] if len(good) >= 2 else None


def parse_flashcards(markdown: str):
    pairs = []
    for block in re.split(r"\n\s*\n", markdown):
        lines = [ln.strip() for ln in block.split("\n") if re.match(r"^\*\*[^*]+:\*\*", ln.strip())]
        if len(lines) >= 2:
            strip = lambda s: re.sub(r"^\*\*[^*]+:\*\*\s*", "", s)  # noqa: E731
            pairs.append((strip(lines[0]), strip(lines[1])))
    return pairs if len(pairs) >= 2 else None


def docx_bytes(markdown: str, title: str) -> bytes:
    from automind.utils.docx_export import markdown_to_docx

    return markdown_to_docx(markdown, title, lang() in ("ur", "sd"))


def selected_ids(svc) -> list[str] | None:
    docs = svc.metadata.list_documents()
    if not docs:
        return None
    chosen = [d.id for d in docs if st.session_state.get(f"use_{d.id}", True)]
    return chosen or None


def rtl_div(text: str) -> str:
    return f'<div dir="auto" class="am-src">{text}</div>'


# ----------------------------------------------------------------------------- sidebar
def sidebar(svc) -> str:
    with st.sidebar:
        st.title("🧠 AutoMind")
        st.selectbox("🌐", options=list(LANGS), format_func=LANGS.get, key="lang",
                     label_visibility="collapsed")
        st.caption(t("tagline"))

        page = st.radio(
            "nav", ["ask", "study", "reader", "settings"], key="page",
            format_func=lambda p: {"ask": "💬 " + t("tabAsk"), "study": "🎓 " + t("tabStudy"),
                                   "reader": "🔊 " + t("tabReader"),
                                   "settings": "⚙️ " + t("settings")}[p],
            label_visibility="collapsed")
        st.divider()

        st.subheader(t("upload"))
        uploads = st.file_uploader(
            t("upload"), accept_multiple_files=True, label_visibility="collapsed",
            help=t("formats"), key=f"uploader_{st.session_state.get('uploader_n', 0)}")
        if uploads:
            notes = []
            for item in uploads:
                with st.spinner(t("reading", name=item.name)):
                    result, error = ingest(svc, item.name, item.getvalue())
                if error:
                    notes.append(("error", f"{item.name}: {error}"))
                elif result.duplicate:
                    notes.append(("info", t("duplicate", name=item.name)))
                else:
                    notes.append(("success", t("uploaded", name=item.name)))
            st.session_state.upload_notes = notes
            st.session_state.uploader_n = st.session_state.get("uploader_n", 0) + 1
            st.rerun()  # clears the uploader so files are not read again on every click
        for kind, text in st.session_state.get("upload_notes", []):
            getattr(st, kind)(text)
        if SAMPLE_DIR.is_dir() and st.button("📚 " + t("loadSample"), use_container_width=True):
            for path in sorted(SAMPLE_DIR.iterdir()):
                ingest(svc, path.name, path.read_bytes())
            st.rerun()

        st.divider()
        st.subheader(t("documents"))
        docs = svc.metadata.list_documents()
        if not docs:
            st.info(t("noDocs"))
        for doc in docs:
            cols = st.columns([6, 1])
            cols[0].checkbox(doc.filename, value=True, key=f"use_{doc.id}",
                             help=f"{t('pagesN', n=doc.n_pages)} · {doc.n_chunks} chunks")
            if cols[1].button("🗑", key=f"del_{doc.id}", help=t("deleteDoc")):
                svc.ingestion.delete(doc.id)
                st.session_state.pop(f"use_{doc.id}", None)
                st.rerun()
        st.caption("🔒 " + t("sessionNote"))

        status = svc.llm_status()
        badge = (f"🟢 {t('connected')}: {status['model']}" if status["real"]
                 else f"⚪ {t('basicMode')}")
        st.caption(badge)
    return page


# ----------------------------------------------------------------------------- study output
def show_sources(sources, question: str) -> None:
    if not sources:
        return
    st.caption(t("sources"))
    for s in sources:
        label = f"[{s.number}] {s.filename} · {t('page')} {s.page}"
        if s.cited:
            label += f"  ✓ {t('cited')}"
        with st.expander(label):
            st.markdown(rtl_div(highlight(s.text, question)), unsafe_allow_html=True)
            st.caption(f"score {s.score}")


def render_study(markdown: str, task: str, uid: str, meta: dict | None = None) -> None:
    paper, _, key = markdown.partition(MARKER)
    has_key = bool(key.strip())

    if meta:
        names = ", ".join(f"{s['filename']} ({', '.join(map(str, s['pages'][:6]))}"
                          f"{'…' if len(s['pages']) > 6 else ''})" for s in meta.get("sources", []))
        if names:
            st.caption(f"{t('sourcesUsed')}: {names}")
        if meta.get("sampled"):
            st.caption(t("sampledNote"))

    cards = parse_flashcards(markdown) if task == "flashcards" else None
    quiz = parse_quiz(markdown) if task == "quiz" else None
    practice = False
    if quiz:
        practice = st.toggle("🎯 " + t("practice"), key=f"practice_{uid}")

    if cards:
        head = re.search(r"^##\s+(.*)$", markdown, re.M)
        if head:
            st.subheader(head.group(1))
        for i, (question, answer) in enumerate(cards, 1):
            with st.expander(f"{i}. {question}"):
                st.markdown(answer)
    elif quiz and practice:
        score = 0
        for q in quiz:
            st.markdown(f"**{q['n']}.** {q['text']}")
            labels = [f"{o['l']}) {o['text']}" for o in q["opts"]]
            choice = st.radio("answer", labels, index=None, key=f"q_{uid}_{q['n']}",
                              label_visibility="collapsed")
            if choice:
                picked = choice[0]
                if picked == q["letter"]:
                    score += 1
                    st.success(t("correct"))
                else:
                    st.error(f"{t('wrong')}. {t('answerIs', a=q['line'])}")
        st.info(t("score", s=score, n=len(quiz)))
    else:
        st.markdown(paper)
        if has_key:
            show = st.toggle(t("showAnswers"), key=f"answers_{uid}")
            if show:
                st.divider()
                st.markdown(key)

    cols = st.columns([1, 1, 4])
    title = t("t_" + task)
    cols[0].download_button("⬇ Word", data=docx_bytes(markdown, title),
                            file_name=f"automind-{task}.docx", key=f"dl_docx_{uid}",
                            mime="application/vnd.openxmlformats-officedocument."
                                 "wordprocessingml.document")
    cols[1].download_button("⬇ .md", data=markdown.replace(MARKER, "\n---\n"),
                            file_name=f"automind-{task}.md", key=f"dl_md_{uid}",
                            mime="text/markdown")


def run_study(svc, fields: dict, holder) -> tuple[dict | None, dict]:
    """Run a study tool and stream its text into `holder`. Returns (final event, meta event)."""
    from automind.generation.study import StudyRequest

    request = StudyRequest(language=lang(), **fields)
    text, meta, final = "", {}, None
    for event in svc.study.run(request):
        kind = event["type"]
        if kind == "meta":
            meta = event
        elif kind == "status":
            holder.info(t("partN", i=event["step"], n=event["total"]))
        elif kind == "token":
            text += event["text"]
            holder.markdown(text.split(MARKER)[0] + " ▌")
        elif kind == "final":
            final = event
    return final, meta


# ----------------------------------------------------------------------------- pages
def page_ask(svc) -> None:
    messages = st.session_state.setdefault("messages", [])
    st.session_state.setdefault("feedback_given", set())

    if not messages:
        st.header(t("welcomeTitle"))
        st.caption(t("welcomeSub"))
        suggestions = ["sugSummary", "sugKey", "sugQuiz", "sugNotes"]
        cols = st.columns(len(suggestions))
        for col, key in zip(cols, suggestions):
            if col.button(t(key), key=f"sug_{key}", use_container_width=True):
                st.session_state.pending_question = t(key)
                st.rerun()
    else:
        if st.button("🧹 " + t("clearChat")):
            st.session_state.messages = []
            st.rerun()

    for i, message in enumerate(messages):
        with st.chat_message(message["role"]):
            if message.get("study"):
                render_study(message["content"], message["task"], f"chat{i}", message.get("meta"))
            else:
                st.markdown(message["content"])
            if message["role"] == "assistant" and not message.get("study"):
                show_sources(message.get("sources", []), message.get("question", ""))
                if message.get("found") and message.get("removed"):
                    st.caption(f"⚠ {t('removedCites')}: {message['removed']}")
                qid = message.get("query_id")
                if qid and message.get("found"):
                    if qid in st.session_state.feedback_given:
                        st.caption(t("thanks"))
                    else:
                        left, right, _ = st.columns([1, 1, 6])
                        if left.button("👍", key=f"up_{qid}", help=t("helpful")):
                            svc.metadata.add_feedback(qid, True, None)
                            st.session_state.feedback_given.add(qid)
                            st.rerun()
                        if right.button("👎", key=f"down_{qid}", help=t("notHelpful")):
                            svc.metadata.add_feedback(qid, False, None)
                            st.session_state.feedback_given.add(qid)
                            st.rerun()

    question = st.chat_input(t("chatPlaceholder")) or st.session_state.pop("pending_question", None)
    if not question:
        return
    if not svc.metadata.list_documents():
        st.warning(t("uploadFirst"))
        return

    messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    ids = selected_ids(svc)

    with st.chat_message("assistant"):
        holder = st.empty()
        holder.markdown("⏳ " + t("thinking"))
        intent = detect_intent(question)
        try:
            if intent:
                final, meta = run_study(svc, {**intent, "document_ids": ids}, holder)
                holder.empty()
                messages.append({"role": "assistant", "content": final["markdown"],
                                 "study": True, "task": intent["task"], "meta": {
                                     "sources": meta.get("sources", []),
                                     "sampled": final.get("sampled")}})
            else:
                history = [(messages[j]["content"][:2000], messages[j + 1]["content"][:6000])
                           for j in range(len(messages) - 2)
                           if messages[j]["role"] == "user"
                           and messages[j + 1]["role"] == "assistant"
                           and messages[j + 1].get("found")][-3:]
                text, sources, answer, query_id = "", [], None, None
                for event in svc.stream_question(question, document_ids=ids, language=lang(),
                                                 history=history):
                    if event["type"] == "sources":
                        sources = event["sources"]
                    elif event["type"] == "token":
                        text += event["text"]
                        holder.markdown(text + " ▌")
                    elif event["type"] == "final":
                        answer, query_id = event["answer"], event["query_id"]
                if answer is not None:
                    text, sources = answer.text, answer.sources
                messages.append({
                    "role": "assistant", "content": text, "sources": sources,
                    "question": question, "query_id": query_id,
                    "found": bool(answer and answer.found),
                    "removed": answer.removed_citations if answer else [],
                })
        except Exception as error:  # noqa: BLE001
            messages.pop()
            holder.error(f"{t('errorGeneric')}: {error}")
            return
    st.rerun()


def page_study(svc) -> None:
    st.header("🎓 " + t("studyTitle"))
    st.caption(t("studySub"))
    docs = svc.metadata.list_documents()
    if not docs:
        st.info(t("pickDocFirst"))
        return

    task = st.radio(
        "tool", TASKS, horizontal=True, key="study_task", label_visibility="collapsed",
        format_func=lambda k: f"{TASK_ICONS[k]} {t('t_' + k)}")
    st.caption(t("d_" + task))

    left, right = st.columns(2)
    topic = left.text_input(t("optTopic"), placeholder=t("optTopicPh"), key="study_topic")
    pages = right.text_input(t("optPages"), placeholder=t("optPagesPh"), key="study_pages")
    c1, c2, c3 = st.columns(3)
    labels = {"easy": t("easy"), "medium": t("medium"), "hard": t("hard"),
              "short": t("short"), "detailed": t("detailed")}
    difficulty = c1.selectbox(t("optDifficulty"), ["easy", "medium", "hard"], index=1,
                              format_func=labels.get, key="study_diff")
    length = c2.selectbox(t("optLength"), ["short", "medium", "detailed"], index=1,
                          format_func=labels.get, key="study_len")
    count = total_marks = None
    if task in ("quiz", "flashcards"):
        count = c3.number_input(t("optCount"), 1, 50, 10 if task == "quiz" else 15,
                                key="study_count")
    elif task in ("assignment", "mid_exam", "final_exam"):
        default = {"assignment": 20, "mid_exam": 30, "final_exam": 60}[task]
        total_marks = c3.number_input(t("optMarks"), 5, 200, default, key=f"study_marks_{task}")
    extra = st.text_area(t("optExtra"), placeholder=t("optExtraPh"), key="study_extra", height=80)

    if st.button("✨ " + t("generate"), type="primary"):
        fields = {"task": task, "document_ids": selected_ids(svc), "topic": topic or None,
                  "pages": pages or None, "instructions": extra or None,
                  "difficulty": difficulty, "length": length,
                  "count": int(count) if count else None,
                  "total_marks": int(total_marks) if total_marks else None}
        holder = st.empty()
        holder.info(t("generating"))
        try:
            final, meta = run_study(svc, fields, holder)
        except Exception as error:  # noqa: BLE001
            holder.error(f"{t('errorGeneric')}: {error}")
        else:
            holder.empty()
            st.session_state.study_out = {
                "markdown": final["markdown"], "task": task,
                "meta": {"sources": meta.get("sources", []), "sampled": final.get("sampled")},
                "uid": st.session_state.get("study_uid", 0) + 1}
            st.session_state.study_uid = st.session_state.study_out["uid"]

    output = st.session_state.get("study_out")
    st.divider()
    if not output:
        st.caption(t("emptyOutput"))
    elif not output["markdown"].strip():
        st.warning(t("emptyOutput"))
    else:
        render_study(output["markdown"], output["task"], f"study{output['uid']}", output["meta"])


READER_HTML = """
<div style="font-family:system-ui,sans-serif;color:#222">
 <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:8px">
  <button id="play" style="padding:6px 14px;border-radius:8px;border:1px solid #ccc;cursor:pointer">▶ __LISTEN__</button>
  <button id="pause" style="padding:6px 14px;border-radius:8px;border:1px solid #ccc;cursor:pointer">⏸ __PAUSE__</button>
  <button id="stop" style="padding:6px 14px;border-radius:8px;border:1px solid #ccc;cursor:pointer">⏹ __STOP__</button>
  <label style="font-size:13px">__SPEED__ <input id="rate" type="range" min="0.6" max="1.6" step="0.1" value="1"></label>
  <select id="voice" style="max-width:220px"></select>
 </div>
 <div id="msg" style="color:#b45309;font-size:13px;margin-bottom:6px"></div>
 <div id="txt" dir="auto" style="max-height:440px;overflow:auto;padding:14px;border:1px solid #ddd;border-radius:10px;background:#fafafa;line-height:2;font-size:17px"></div>
</div>
<script>
const sentences = __SENTENCES__, LANG = "__LANG__", NOVOICE = __NOVOICE__, NOSPEECH = __NOSPEECH__, AUTO = "__AUTO__";
const box = document.getElementById("txt"), sel = document.getElementById("voice"), msg = document.getElementById("msg");
const synth = window.speechSynthesis; let idx = 0, playing = false, voices = [];
sentences.forEach((s, i) => { const el = document.createElement("span"); el.textContent = s + " "; el.style.cursor = "pointer"; el.style.padding = "1px 2px"; el.style.borderRadius = "4px"; el.id = "s" + i; el.onclick = () => { stop(); idx = i; play(); }; box.appendChild(el); });
function fill() {
  voices = synth ? synth.getVoices() : [];
  const base = LANG.slice(0, 2), fallbacks = base === "sd" ? ["sd", "ur", "ar"] : [base];
  const usable = voices.filter(v => fallbacks.some(f => v.lang.toLowerCase().startsWith(f)));
  sel.innerHTML = ""; sel.append(new Option(AUTO, "-1"));
  usable.forEach(v => sel.append(new Option(v.name + " (" + v.lang + ")", voices.indexOf(v))));
  msg.textContent = usable.length ? "" : NOVOICE;
}
if (!synth) { msg.textContent = NOSPEECH; } else { fill(); synth.onvoiceschanged = fill; }
function mark(i) { document.querySelectorAll("#txt span").forEach(e => e.style.background = ""); const el = document.getElementById("s" + i); if (el) { el.style.background = "#ffe58a"; el.scrollIntoView({block: "nearest"}); } }
function play() {
  if (!synth || idx >= sentences.length) { playing = false; return; }
  playing = true; synth.cancel(); mark(idx);
  const u = new SpeechSynthesisUtterance(sentences[idx]); u.lang = LANG; u.rate = parseFloat(document.getElementById("rate").value);
  const v = voices[parseInt(sel.value)]; if (v) { u.voice = v; u.lang = v.lang; }
  u.onend = () => { if (playing) { idx++; play(); } };
  synth.speak(u);
}
function stop() { playing = false; if (synth) synth.cancel(); }
document.getElementById("play").onclick = () => { if (synth && synth.paused) synth.resume(); else { stop(); play(); } };
document.getElementById("pause").onclick = () => synth && synth.pause();
document.getElementById("stop").onclick = () => { stop(); idx = 0; mark(-1); };
window.addEventListener("beforeunload", stop);
</script>
"""


def page_reader(svc) -> None:
    st.header("🔊 " + t("readerTitle"))
    st.caption(t("readerSub"))
    docs = svc.metadata.list_documents()
    if not docs:
        st.info(t("noDocs"))
        return
    names = {d.id: d.filename for d in docs}
    doc_id = st.selectbox(t("chooseDoc"), list(names), format_func=names.get, key="reader_doc")
    pages = svc.document_pages(doc_id) or []
    if not pages:
        st.warning(t("emptyOutput"))
        return
    number = st.selectbox(
        t("page"), [p["page"] for p in pages], key=f"reader_page_{doc_id}",
        format_func=lambda n: t("pageOf", p=n, n=pages[-1]["page"]))
    text = next(p["text"] for p in pages if p["page"] == number)
    sentences = [s.strip() for s in re.split(r"(?<=[.!?۔؟])\s+|\n{2,}", text) if s.strip()]

    page_html = (READER_HTML
                 .replace("__SENTENCES__", json.dumps(sentences, ensure_ascii=False))
                 .replace("__LANG__", I18N[lang()]["speech"])
                 .replace("__NOVOICE__", json.dumps(t("noVoice"), ensure_ascii=False))
                 .replace("__NOSPEECH__", json.dumps(t("noSpeech"), ensure_ascii=False))
                 .replace("__AUTO__", t("autoVoice"))
                 .replace("__LISTEN__", t("listen")).replace("__PAUSE__", t("pause"))
                 .replace("__STOP__", t("stopSpeech")).replace("__SPEED__", t("speed")))
    components.html(page_html, height=620, scrolling=False)


def page_settings(svc) -> None:
    st.header("⚙️ " + t("settings"))
    st.caption(t("settingsSub"))
    status = svc.llm_status()
    st.info((f"🟢 {t('connected')}: {status['name']}" if status["real"] else f"⚪ {t('basicMode')}")
            + f"  ·  {t('searchMode')}: "
            + (t("searchSemantic") if status["semantic_search"] else t("searchWords")))
    if st.session_state.get("secret_error"):
        st.warning(st.session_state.secret_error)

    keys = [k for k in PRESETS if k != "ollama" or os.getenv("AUTOMIND_SHOW_OLLAMA")]
    choice = st.selectbox(t("provider"), keys, format_func=lambda k: t(PRESET_LABEL[k]),
                          key="preset")
    preset = PRESETS[choice]
    if preset["provider"] == "extractive":
        if st.button(t("saveTest"), type="primary"):
            svc.configure_llm({"provider": "extractive"}, test=False)
            st.rerun()
        return

    model = st.text_input(t("modelName"), value=preset.get("model", ""), key=f"model_{choice}")
    base = st.text_input(t("baseUrl"), value=preset.get("base", ""), key=f"base_{choice}")
    key = ""
    if preset["provider"] == "openai":
        key = st.text_input(t("apiKey"), type="password", key=f"key_{choice}",
                            help=t("keyHintCloud"))
        st.caption("🔑 " + t("keyHintCloud"))

    if st.button(t("saveTest"), type="primary"):
        from automind.generation.llm_client import LLMError

        config = {"provider": preset["provider"], "model": model or None}
        if preset["provider"] == "ollama":
            config["ollama_url"] = base or None
        else:
            config["base_url"] = base or None
            config["api_key"] = key or None
        try:
            with st.spinner(t("saving")):
                svc.configure_llm(config, test=True)
        except LLMError as error:
            st.error(str(error))
        else:
            st.success(t("connected"))
            st.rerun()


# ----------------------------------------------------------------------------- main
def main() -> None:
    svc = get_services()
    page = sidebar(svc)
    inject_css()
    {"ask": page_ask, "study": page_study, "reader": page_reader,
     "settings": page_settings}[page](svc)


main()
