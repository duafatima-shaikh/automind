FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Use EXTRAS="" for a small image that uses the offline hash embeddings.
ARG EXTRAS=ml,ocr
# Set to true to also read old .doc, .ppt and .xls files (adds several hundred megabytes).
ARG INSTALL_LIBREOFFICE=false
RUN apt-get update && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 \
    && if [ "$INSTALL_LIBREOFFICE" = "true" ]; then apt-get install -y --no-install-recommends libreoffice-core libreoffice-writer libreoffice-impress libreoffice-calc; fi \
    && rm -rf /var/lib/apt/lists/*
COPY pyproject.toml README.md ./
COPY src ./src
RUN if [ -n "$EXTRAS" ]; then pip install ".[${EXTRAS}]"; else pip install .; fi

ENV AUTOMIND_DATA_DIR=/data
VOLUME ["/data"]
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')"

CMD ["uvicorn", "automind.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
