from tests.conftest import SAMPLE_TEXT
from tests.fixtures.make_pdf import make_pdf


def upload(client, name="bikes.txt", content=SAMPLE_TEXT.encode()):
    return client.post("/upload", files={"file": (name, content)})


def test_health_starts_empty(client):
    body = client.get("/health").json()
    assert body["status"] == "ok" and body["documents"] == 0


def test_upload_query_with_citations(client):
    response = upload(client)
    assert response.status_code == 201
    assert response.json()["n_chunks"] >= 1

    result = client.post("/query", json={"question": "How much does the monthly pass cost?"}).json()
    assert result["found"] is True
    assert "18 dollars" in result["answer"]
    assert result["citation_check"]["valid"] == [1]
    assert result["citation_check"]["removed"] == []
    assert result["sources"][0]["cited"] is True
    assert result["sources"][0]["filename"] == "bikes.txt"


def test_unanswerable_question_is_refused(client):
    upload(client)
    result = client.post("/query", json={"question": "Who painted the Mona Lisa?"}).json()
    assert result["found"] is False
    assert "could not find" in result["answer"].lower()


def test_duplicate_upload_is_detected(client):
    first = upload(client).json()
    again = upload(client)
    assert again.status_code == 200
    assert again.json()["duplicate"] is True and again.json()["id"] == first["id"]
    assert len(client.get("/documents").json()) == 1


def test_pdf_upload_keeps_page_numbers(client):
    pdf = make_pdf(["Intro page about nothing in particular.",
                    "The ideal water temperature for coffee is 93 degrees Celsius."])
    assert upload(client, "guide.pdf", pdf).status_code == 201
    result = client.post("/query", json={"question": "What is the ideal water temperature for coffee?"}).json()
    assert result["found"] and result["sources"][0]["page"] == 2


def test_query_can_be_limited_to_documents(client):
    first = upload(client, "a.txt", b"Alpha document says the gate code is 4711.").json()
    upload(client, "b.txt", b"Bravo document says the gate code is 9999.")
    result = client.post("/query", json={"question": "What is the gate code?",
                                         "document_ids": [first["id"]]}).json()
    assert {s["doc_id"] for s in result["sources"]} == {first["id"]}
    assert "4711" in result["answer"]


def test_delete_document_removes_its_content(client):
    doc = upload(client).json()
    assert client.delete(f"/documents/{doc['id']}").status_code == 204
    assert client.get(f"/documents/{doc['id']}").status_code == 404
    result = client.post("/query", json={"question": "How much does the monthly pass cost?"}).json()
    assert result["found"] is False and result["sources"] == []
    assert client.delete(f"/documents/{doc['id']}").status_code == 404


def test_bad_uploads(client):
    assert upload(client, "x.exe", b"MZ\x90\x00" + bytes(range(256))).status_code == 415
    assert upload(client, "empty.txt", b"   ").status_code == 422
    assert client.post("/upload", files={"file": ("e.txt", b"")}).status_code == 400


def test_query_validation(client):
    assert client.post("/query", json={"question": "hi"}).status_code == 422


def test_streaming_events(client):
    upload(client)
    with client.stream("POST", "/query/stream", json={"question": "How much does the monthly pass cost?"}) as r:
        body = "".join(r.iter_text())
    events = [line[7:] for line in body.splitlines() if line.startswith("event: ")]
    assert events[0] == "sources" and events[-1] == "final" and "token" in events


def test_feedback_and_metrics(client):
    upload(client)
    query_id = client.post("/query", json={"question": "How much does the monthly pass cost?"}).json()["query_id"]
    assert client.post("/feedback", json={"query_id": query_id, "helpful": True}).status_code == 200
    assert client.post("/feedback", json={"query_id": "nope", "helpful": True}).status_code == 404
    metrics = client.get("/metrics").json()
    assert metrics["counters"]["queries_total"] >= 1
    assert metrics["feedback"]["helpful"] == 1
    assert "retrieval" in metrics["timings"]


def test_data_survives_restart(settings):
    from fastapi.testclient import TestClient

    from automind.api.main import create_app

    with TestClient(create_app(settings)) as first:
        upload(first)
    with TestClient(create_app(settings)) as second:
        assert len(second.get("/documents").json()) == 1
        result = second.post("/query", json={"question": "How much does the monthly pass cost?"}).json()
        assert result["found"] is True


def test_upload_spreadsheet_and_ask_about_a_row(client):
    import io

    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Stations"
    sheet.append(["Station", "Trips per weekday"])
    sheet.append(["Central Library", 1200])
    sheet.append(["River Park", 640])
    buffer = io.BytesIO()
    workbook.save(buffer)
    assert upload(client, "stations.xlsx", buffer.getvalue()).status_code == 201
    result = client.post("/query", json={"question": "How many trips per weekday at River Park?"}).json()
    assert result["found"] and "640" in result["answer"]
    assert result["sources"][0]["filename"] == "stations.xlsx"


def test_upload_presentation_cites_the_slide_number(client):
    import io

    from pptx import Presentation

    presentation = Presentation()
    for title, body in (("Intro", "Welcome everyone"), ("Safety", "Helmets are recommended for all riders")):
        slide = presentation.slides.add_slide(presentation.slide_layouts[1])
        slide.shapes.title.text = title
        slide.placeholders[1].text = body
    buffer = io.BytesIO()
    presentation.save(buffer)
    assert upload(client, "deck.pptx", buffer.getvalue()).status_code == 201
    result = client.post("/query", json={"question": "Which riders are recommended to wear helmets?"}).json()
    assert result["found"] and result["sources"][0]["page"] == 2


def test_upload_image_and_ask_about_its_text(client):
    import io

    import pytest
    pytest.importorskip("rapidocr_onnxruntime")
    from PIL import Image, ImageDraw, ImageFont

    image = Image.new("RGB", (950, 140), "white")
    ImageDraw.Draw(image).text((20, 30), "The gate code is 4711", fill="black",
                               font=ImageFont.load_default(size=44))
    buffer = io.BytesIO()
    image.save(buffer, "PNG")
    response = upload(client, "sign.png", buffer.getvalue())
    assert response.status_code == 201
    result = client.post("/query", json={"question": "What is the gate code?"}).json()
    assert result["found"] and "4711" in result["answer"]


def test_missing_text_recognition_returns_501(client, monkeypatch):
    import io

    from PIL import Image

    from automind.ingestion.ocr import OCRUnavailable

    def unavailable(*args, **kwargs):
        raise OCRUnavailable("Reading text from images needs a text recognition engine.")

    monkeypatch.setattr("automind.ingestion.ocr.ocr_image", unavailable)
    buffer = io.BytesIO()
    Image.new("RGB", (40, 40)).save(buffer, "PNG")
    response = upload(client, "pic.png", buffer.getvalue())
    assert response.status_code == 501
    assert "text recognition" in response.json()["detail"]
