# ADR-001: Tech stack for a low-cost, self-hosted RAG on a shared VPS

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 7 Nov 2026 |
| Decider | Kovarthanan Murugan |

## Context

EPF Mitra must answer EPF/EPS questions from thousands of EPFO pages, as a public demo, under these constraints (from the [BRD](../BRD.md)):

- **Budget:** under ₹300 per month in total.
- **Infrastructure:** a shared Hostinger VPS (7.8 GB RAM, no GPU, 91 GB free disk) already running n8n, Traefik and another RAG app. EPF Mitra's always-running services must stay under about 2 GB of RAM.
- **Quality:** answers must be grounded in official documents, cite their source, and prefer the newest rule.
- **Timeline:** v1 in 14 days, built by one developer.

The guiding principle: **run everything that can run for free on the VPS locally, and pay only for answer generation.**

## Decisions

| Area | Decision | Alternatives considered | Why this choice |
|---|---|---|---|
| Frontend | **Angular 17+** (standalone components, Signals) | Streamlit, React | Owner's main strength (10+ years); production-grade UI; shows frontend + AI skills together |
| Backend | **FastAPI** (Python) | Node.js/Express | Python has the best AI libraries; async and Server-Sent Events for streaming; automatic API docs |
| Embeddings | **BGE-small-en-v1.5, run locally** with FastEmbed (ONNX, CPU) | OpenAI `text-embedding-3-small` | Free; no data sent outside for indexing; small (384 dimensions, low RAM); good retrieval quality for English |
| Keyword search | **BM25 sparse vectors** stored in Qdrant | Separate Elasticsearch / OpenSearch | Gives hybrid search without running another heavy service |
| Vector database | **Qdrant** (Docker, on-disk storage) | FAISS, Chroma, pgvector | Dense and sparse vectors in one store; metadata filters (date, document type); on-disk mode keeps RAM low |
| Re-ranking | **FlashRank** (small CPU model) | Cohere Rerank (paid API), large cross-encoders | Free and light enough for the VPS CPU |
| LLM | **GPT-4o-mini** behind a small provider interface | Gemini Flash, Groq, local models via Ollama | Very low cost per answer, good instruction following; already in use; the interface allows switching provider if prices change. A local LLM is too slow on a CPU-only VPS |
| Orchestration | **Plain Python modules** in v1 | LangChain chains, LangGraph | The v1 flow is a fixed pipeline; plain code is easier to test, debug and explain. LangGraph is planned for v2 multi-step questions |
| PDF parsing | **PyMuPDF**, plus **Tesseract OCR** for scanned pages | Docling, Unstructured, LlamaParse | Fast and light; Docling/Unstructured need more RAM; LlamaParse is a paid API |
| Answer cache | **SQLite**, exact match on the normalised question | Redis, semantic cache | No extra service to run; EPF questions repeat often. Semantic cache in v2 |
| Rate limiting | **In-app limiter** keyed on a hashed IP | Limits in Traefik, API gateway | Simple; supports the custom message and daily caps from the PRD |
| Evaluation | **RAGAS** with GPT-4o-mini as the judge, run manually | Manual review only | Repeatable accuracy numbers at very low cost |
| Monitoring | **LangSmith** free tier + structured logs | Self-hosted Langfuse | No extra container to run |
| Deployment | **Docker Compose** with memory limits, behind the existing **Traefik**; CI with **GitHub Actions** | Kubernetes, managed cloud | Fits a single VPS; reuses existing HTTPS setup |

## Cost estimate (monthly)

| Item | Cost |
|---|---|
| VPS | ₹0 extra (already paid) |
| Embeddings, vector DB, re-ranker, OCR | ₹0 (run locally) |
| LLM: ~2,500 input + ~300 output tokens per answer, ~1,000 answers/month | ≈ ₹50 (prices change; check current rates) |
| Evaluation runs | ≈ ₹20–50 |
| **Total** | **Well under ₹300**, with a hard API spending cap of $5 per month |

## Consequences

**Good**

- Running cost stays very low; only answer generation is paid.
- All parts except the LLM are open source and self-hosted; no lock-in.
- Memory limits protect the other services on the shared VPS.

**Trade-offs**

- BGE-small supports English well, but not Tamil; Tamil support (v2) will need a multilingual embedding model and re-indexing.
- CPU-only re-ranking and embedding add some latency (expected under 1 second).
- An exact-match cache misses reworded questions; a semantic cache is planned for v2.
- Depending on one LLM provider; mitigated by the provider interface.

## Review

Revisit this decision if monthly traffic exceeds about 10,000 questions, if Tamil support starts, or if LLM prices change significantly.
