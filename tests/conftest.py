import pytest
from fastapi.testclient import TestClient

from automind.api.main import create_app
from automind.config import Settings


@pytest.fixture
def settings(tmp_path):
    return Settings(
        data_dir=tmp_path / "data",
        embedding_backend="hash",
        chunk_size=300,
        chunk_overlap=60,
        use_faiss=False,
        llm_provider="extractive",
    )


@pytest.fixture
def client(settings):
    app = create_app(settings)
    with TestClient(app) as test_client:
        yield test_client


SAMPLE_TEXT = (
    "The Marlow bike share program launched in March 2019 with 400 bicycles. "
    "A monthly pass costs 18 dollars and includes unlimited rides of up to 45 minutes. "
    "The busiest station is Central Library, with more than 1,200 trips on a weekday. "
    "Helmets are not required by law but are recommended."
)
