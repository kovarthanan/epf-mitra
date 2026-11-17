# EPF Mitra API: FastAPI + hybrid retriever (Chroma, BM25, FlashRank) + OpenAI
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    HF_HOME=/app/data/hf_cache \
    TOKENIZERS_PARALLELISM=false

WORKDIR /app

# CPU-only PyTorch first: avoids pulling ~2 GB of CUDA libraries for sentence-transformers
RUN pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
COPY api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt

COPY rag/ rag/
COPY api/ api/

# data/ (chroma, chunks.jsonl, manifest.jsonl, model caches) is mounted as a volume
RUN useradd --create-home appuser && mkdir -p /app/data && chown -R appuser /app
USER appuser

EXPOSE 8000
CMD ["uvicorn", "api.server:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
