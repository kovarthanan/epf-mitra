# EPF Mitra

**An AI assistant that answers EPF and EPS questions from official EPFO documents, with a citation for every answer.**

> 🚧 Work in progress: being built in public over 14 days (Nov 2026).

## The problem

Millions of salaried employees in India have questions about their Provident Fund: how much they can withdraw, when, whether they qualify for a pension, and what changed in the 2026 rules. The answers are spread across hundreds of EPFO circulars, FAQs and scheme documents that are hard to search and hard to read.

## What EPF Mitra does

- Answers EPF / EPS questions in plain language
- Cites the official source (document and page) for every answer
- Says "I don't know" when the documents don't cover a question
- Checks PF withdrawal eligibility with a simple form (no AI needed)

## Architecture (planned)

```
EPFO website ─▶ Ingestion pipeline ─▶ Chunks + embeddings ─▶ Qdrant (vector DB)
                (download, parse,                                  │
                 OCR, dedupe)                                      ▼
Angular UI ◀── streaming ── FastAPI ◀── hybrid search + re-rank ◀──┘
                              │
                              └─▶ LLM (answer generation with citations)
```

## Tech stack (planned)

| Layer | Technology |
|---|---|
| Frontend | Angular 17+ (standalone components, Signals) |
| Backend | FastAPI (Python) |
| Retrieval | Hybrid search (BM25 + vectors), FlashRank re-ranking |
| Embeddings | BGE-small (local, free) |
| Vector DB | Qdrant |
| LLM | GPT-4o-mini |
| Evaluation | RAGAS |
| Deployment | Docker, GitHub Actions, Traefik on a VPS |

## Project structure

```
epf-mitra/
├── docs/          BRD, PRD, architecture, decision records (ADRs)
├── ingest/        Download and parse EPFO documents
├── rag/           Chunking, embeddings, retrieval, answer generation
├── api/           FastAPI backend
├── ui/            Angular frontend
├── eval/          Evaluation test set and scores
├── infra/         Docker and deployment config
├── tests/         Unit tests
└── data/          Raw and processed documents (not committed)
```

## Documentation

- [Business Requirements (BRD)](docs/BRD.md)

## Disclaimer

EPF Mitra is an independent learning project. It is not affiliated with EPFO or the Government of India. Answers are for information only: always verify on [epfindia.gov.in](https://www.epfindia.gov.in) before making financial decisions.

## Author

**Kovarthanan Murugan**: Lead Frontend Engineer (Angular) building AI applications · [GitHub](https://github.com/kovarthanan)
