"""AutoMind chat screen (Streamlit). Run with: streamlit run frontend/app.py"""
from __future__ import annotations

import html
import json
import os
import re

import requests
import streamlit as st

API_URL = os.getenv("AUTOMIND_API_URL", "http://localhost:8000").rstrip("/")
IGNORED_WORDS = {
    "the", "and", "for", "are", "was", "what", "which", "how", "does", "with", "that", "this",
    "from", "have", "has", "who", "why", "when", "where", "much", "many", "can", "you", "your",
}

st.set_page_config(page_title="AutoMind", page_icon="🤖", layout="wide")


def api_get(path: str):
    response = requests.get(f"{API_URL}{path}", timeout=15)
    response.raise_for_status()
    return response.json()


def highlight(text: str, question: str) -> str:
    """Show the source text with the question's words marked."""
    safe = html.escape(text)
    words = {w for w in re.findall(r"[A-Za-z0-9]+", question.lower())
             if len(w) > 2 and w not in IGNORED_WORDS}
    if not words:
        return safe
    pattern = re.compile(r"\b(" + "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True)) + r")\b",
                         re.IGNORECASE)
    return pattern.sub(r"<mark>\1</mark>", safe)


def stream_query(question: str, document_ids: list[str] | None):
    payload = {"question": question, "document_ids": document_ids or None}
    with requests.post(f"{API_URL}/query/stream", json=payload, stream=True, timeout=180) as response:
        response.raise_for_status()
        event = None
        for line in response.iter_lines(decode_unicode=True):
            if not line:
                continue
            if line.startswith("event:"):
                event = line[6:].strip()
            elif line.startswith("data:"):
                yield event, json.loads(line[5:].strip())


def send_feedback(query_id: str, helpful: bool) -> None:
    try:
        requests.post(f"{API_URL}/feedback", json={"query_id": query_id, "helpful": helpful},
                      timeout=10).raise_for_status()
        st.session_state.feedback_given.add(query_id)
    except requests.RequestException as error:
        st.session_state.last_error = f"Could not save feedback: {error}"


def show_sources(sources: list[dict], question: str) -> None:
    if not sources:
        return
    st.caption("Sources")
    for source in sources:
        label = f"[{source['number']}] {source['filename']}, page {source['page']}"
        if source["cited"]:
            label += "  (cited)"
        with st.expander(label, expanded=False):
            st.markdown(highlight(source["text"], question), unsafe_allow_html=True)
            st.caption(f"Match score {source['score']}")


# ---- state ----
st.session_state.setdefault("messages", [])
st.session_state.setdefault("feedback_given", set())
st.session_state.setdefault("last_error", None)

# ---- sidebar: documents ----
with st.sidebar:
    st.title("🤖 AutoMind")
    st.caption("Ask questions about your documents.")
    uploaded = st.file_uploader("Upload documents or images", accept_multiple_files=True,
                                help="PDF, Word, PowerPoint, Excel, CSV, images, text and more")
    if uploaded and st.button("Add to library", type="primary"):
        for item in uploaded:
            try:
                response = requests.post(f"{API_URL}/upload", files={"file": (item.name, item.getvalue())},
                                         timeout=300)
                if response.ok:
                    info = response.json()
                    note = "already in the library" if info["duplicate"] else f"{info['n_chunks']} chunks"
                    st.success(f"{item.name}: {note}")
                else:
                    st.error(f"{item.name}: {response.json().get('detail', response.text)}")
            except requests.RequestException as error:
                st.error(f"{item.name}: {error}")

    st.divider()
    st.subheader("Library")
    try:
        documents = api_get("/documents")
    except requests.RequestException:
        documents = []
        st.error(f"Cannot reach the API at {API_URL}")
    selected_ids = []
    for document in documents:
        columns = st.columns([5, 1])
        if columns[0].checkbox(document["filename"], value=True, key=f"use_{document['id']}",
                               help=f"{document['n_pages']} pages, {document['n_chunks']} chunks"):
            selected_ids.append(document["id"])
        if columns[1].button("🗑", key=f"del_{document['id']}", help="Delete this document"):
            requests.delete(f"{API_URL}/documents/{document['id']}", timeout=30)
            st.rerun()
    if not documents:
        st.info("No documents yet. Upload one to begin.")
    if st.button("Clear chat"):
        st.session_state.messages = []
        st.rerun()

# ---- chat history ----
st.header("Ask your documents")
if st.session_state.last_error:
    st.warning(st.session_state.last_error)
    st.session_state.last_error = None

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])
        if message["role"] == "assistant":
            show_sources(message.get("sources", []), message.get("question", ""))
            query_id = message.get("query_id")
            if query_id and message.get("found"):
                if query_id in st.session_state.feedback_given:
                    st.caption("Thanks for your feedback.")
                else:
                    left, right, _ = st.columns([1, 1, 8])
                    left.button("👍", key=f"up_{query_id}", on_click=send_feedback, args=(query_id, True))
                    right.button("👎", key=f"down_{query_id}", on_click=send_feedback, args=(query_id, False))

# ---- new question ----
question = st.chat_input("Ask a question about your documents")
if question:
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.write(question)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        text, sources, final = "", [], None
        try:
            for event, data in stream_query(question, selected_ids if documents else None):
                if event == "sources":
                    sources = data["sources"]
                elif event == "token":
                    text += data["text"]
                    placeholder.write(text + "▌")
                elif event == "final":
                    final = data
                elif event == "error":
                    raise RuntimeError(data["message"])
        except (requests.RequestException, RuntimeError) as error:
            placeholder.error(f"Something went wrong: {error}")
        else:
            if final:
                text, sources = final["answer"], final["sources"]
            placeholder.write(text)
            st.session_state.messages.append({
                "role": "assistant", "content": text, "sources": sources, "question": question,
                "query_id": final["query_id"] if final else None,
                "found": final["found"] if final else False,
            })
            st.rerun()
