"""Load the four sample documents into your AutoMind data folder, so you can try questions
right away.   Usage: python scripts/ingest_sample.py"""
from __future__ import annotations

from automind.config import get_settings
from automind.evaluation.run_eval import DATASETS
from automind.services import Services


def main() -> None:
    services = Services(get_settings())
    try:
        for path in sorted((DATASETS / "sample_docs").iterdir()):
            result = services.ingestion.ingest(path.name, path.read_bytes())
            status = "already there" if result.duplicate else f"{result.document.n_chunks} chunks"
            print(f"{path.name}: {status}")
    finally:
        services.close()


if __name__ == "__main__":
    main()
