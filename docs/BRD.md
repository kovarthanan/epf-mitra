# Business Requirements Document (BRD): EPF Mitra

| Field | Value |
|---|---|
| Project | EPF Mitra |
| Owner | Kovarthanan Murugan |
| Version | 0.1 (draft) |
| Date | 6 Nov 2026 |
| Status | Draft for review |

---

## 1. Purpose

This document describes **why** EPF Mitra is being built, **who** it is for, and **how success will be measured**. It does not describe how the system is built: that belongs in the PRD and the architecture document.

## 2. Problem statement

Salaried employees in India regularly need answers about their Employees' Provident Fund (EPF) and Employees' Pension Scheme (EPS), for example:

- How much PF can I withdraw after leaving a job, and when?
- Do I qualify for a monthly pension, or only a lump sum?
- How do I transfer my old PF account to my new employer?
- What changed in the 2026 withdrawal rules?

Today, the official answers are spread across many EPFO circulars, FAQs and scheme documents, mostly as PDFs. They are:

- **Hard to find:** there is no single place to ask a question in plain language.
- **Hard to read:** written in legal language, sometimes as scanned documents.
- **Frequently updated:** older blog posts and forums often give outdated answers.

As a result, people rely on guesswork, unofficial sources, or paid agents, and sometimes make costly mistakes (for example, withdrawing PF when it would be taxed, or losing pension service years).

## 3. Target users

| User | Need | Example question |
|---|---|---|
| **Salaried employee** (primary) | Quick, trustworthy answers about their own PF | "I left my job 3 months ago. How much can I withdraw?" |
| **Job changer / between jobs** | Understand withdrawal vs transfer, tax, pension impact | "Should I withdraw or transfer my PF?" |
| **HR / payroll staff** (secondary) | Answer employees' repeated PF questions | "Is a pre-existing EPS member eligible to continue EPS?" |

## 4. Business goals

1. Give users **accurate, source-backed answers** to common EPF/EPS questions in seconds.
2. Build user **trust** by citing the official document for every answer.
3. Demonstrate **production-grade AI engineering** (data pipeline, retrieval, evaluation, deployment) as a public portfolio project.

## 5. Success metrics

| Metric | Target for v1 |
|---|---|
| Answer accuracy on a 30-question test set (RAGAS faithfulness) | ≥ 0.85 |
| Answers that include a valid citation | 100% |
| Correct "I don't know" for out-of-scope questions | ≥ 90% |
| Response time (first words appear) | < 3 seconds |
| Running cost | < ₹300 per month |
| Public demo users in the first month | 100+ |

## 6. Scope

### In scope (v1)

- Questions about EPF and EPS, answered from official EPFO documents
- A citation (document title and page) with every answer
- Withdrawal eligibility checker (rule-based form)
- English language
- Public web demo with usage limits

### Out of scope (v1)

- Logging into EPFO or accessing anyone's personal PF account
- Filing claims or submitting forms on a user's behalf
- Personal financial or legal advice
- Tamil and other languages (planned for v2)
- Other schemes such as ESI or NPS

## 7. Constraints

- **Budget:** total running cost under ₹300 per month, with a hard API spending cap.
- **Infrastructure:** must run on an existing shared VPS alongside other services, within about 2 GB of RAM.
- **Data:** only publicly available official documents; no personal data is collected.
- **Timeline:** working v1 in 14 days (6–19 Nov 2026).

## 8. Assumptions

- EPFO documents remain publicly available on the official website.
- Most user questions repeat, so caching common answers will reduce cost.
- Users accept answers in English for v1.

## 9. Risks and mitigations

| Risk | Impact | Mitigation |
|---|---|---|
| Wrong or outdated answer | Users make bad financial decisions | Citations on every answer, evaluation test set, disclaimer, "verify on epfindia.gov.in" |
| Rules change after documents are indexed | Answers become outdated | Store document dates; show "as of" date; re-ingest new circulars |
| API costs grow with traffic | Exceeds budget | Answer cache, per-user and daily limits, hard spending cap |
| Prompt injection or misuse | Off-topic or harmful output | Guardrails and topic restriction |
| Scanned or messy PDFs | Missing or wrong text | OCR, parsing checks, logging of failed documents |

## 10. Stakeholders

| Role | Person |
|---|---|
| Product owner, architect, developer | Kovarthanan Murugan |
| End users | Salaried employees, HR staff |

## 11. Open questions

- [ ] Which EPFO documents are in scope for v1 (circulars from which year onwards)?
- [ ] Should answers show the date of the rule they are based on?
- [ ] What is the daily question limit per user for the public demo?
