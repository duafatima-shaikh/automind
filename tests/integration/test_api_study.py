import io

from docx import Document

DOC = (
    "The Marlow bike share program launched in March 2019 with 400 bicycles and 40 docking "
    "stations. A monthly pass costs 18 dollars and includes unlimited rides of up to 45 minutes. "
    "The busiest station is Central Library, with more than 1,200 trips on a weekday."
)


def upload(client, name="bikes.txt", text=DOC):
    return client.post("/upload", files={"file": (name, text.encode())}).json()


def test_home_page_and_static_files_are_served(client):
    page = client.get("/")
    assert page.status_code == 200 and "AutoMind" in page.text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/app.css").status_code == 200


def test_study_endpoint_returns_markdown(client):
    upload(client)
    result = client.post("/study", json={"task": "quiz", "count": 3}).json()
    assert result["offline"] is True
    assert "---ANSWERS---" in result["markdown"]
    assert result["sources"][0]["filename"] == "bikes.txt"


def test_study_rejects_unknown_tasks_and_empty_library(client):
    assert client.post("/study", json={"task": "dance"}).status_code == 422
    assert client.post("/study", json={"task": "summary"}).status_code == 422  # nothing uploaded


def test_study_stream_events(client):
    upload(client)
    with client.stream("POST", "/study/stream", json={"task": "summary", "language": "ur"}) as r:
        body = "".join(r.iter_text())
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "meta" and events[-1] == "final" and "token" in events
    assert "خلاصہ" in body


def test_query_accepts_language_and_history(client):
    upload(client)
    result = client.post("/query", json={
        "question": "How much is a monthly pass?", "language": "sd",
        "history": [{"question": "What is Marlow?", "answer": "A bike share program."}],
    }).json()
    assert result["found"] is True


def test_query_rejects_unknown_language(client):
    upload(client)
    assert client.post("/query", json={"question": "How much is a monthly pass?",
                                       "language": "fr"}).status_code == 422


def test_document_text_endpoint(client):
    doc = upload(client)
    body = client.get(f"/documents/{doc['id']}/text").json()
    assert body["filename"] == "bikes.txt" and "Marlow" in body["pages"][0]["text"]
    assert client.get("/documents/nope/text").status_code == 404


def test_llm_settings_roundtrip_never_leaks_a_key(client):
    status = client.get("/settings/llm").json()
    assert status["provider"] == "extractive" and "api_key" not in status
    bad = client.post("/settings/llm", json={"provider": "openai", "model": "gpt-4o-mini"})
    assert bad.status_code == 400
    ok = client.post("/settings/llm", json={"provider": "extractive"})
    assert ok.status_code == 200 and ok.json()["real"] is False


def test_export_docx(client):
    response = client.post("/export/docx", json={"markdown": "## Hello\n\n- one", "title": "T"})
    assert response.status_code == 200
    assert "wordprocessingml" in response.headers.get("content-type", response.headers.get("Content-Type", ""))
    assert any(p.text == "Hello" for p in Document(io.BytesIO(response.content)).paragraphs)
