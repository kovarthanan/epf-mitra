# Product Requirements Document (PRD): EPF Mitra

| Field | Value |
|---|---|
| Product | EPF Mitra |
| Owner | Kovarthanan Murugan |
| Version | 0.1 (draft) |
| Date | 7 Nov 2026 |
| Related | [BRD](BRD.md) |

---

## 1. Overview

EPF Mitra is a web app where anyone can ask a question about EPF or EPS in plain English and get a short answer based on official EPFO documents, with the source and rule date shown. It also includes a simple form that checks PF withdrawal eligibility without using AI.

The BRD explains **why** we are building this. This PRD explains **what** the product does.

## 2. Personas

| Persona | Situation | Goal |
|---|---|---|
| **Ravi, 32, software engineer** | Changing jobs next month | Decide whether to transfer or withdraw his PF |
| **Priya, 38, between jobs** | Left her company 4 months ago | Know how much PF she can withdraw now and whether it is taxed |
| **Suresh, 45, HR executive** | Gets the same PF questions from employees every week | Get a quick, sourced answer to share with employees |

## 3. User stories

Priority uses MoSCoW: **Must** (v1 cannot launch without it), **Should** (important, in v1 if time allows), **Could** (nice to have), **Won't** (not in v1).

### Ask a question

| ID | User story | Priority |
|---|---|---|
| US-01 | As a user, I want to type a PF question in plain English, so that I don't have to search through circulars. | Must |
| US-02 | As a user, I want to see the answer appear as it is generated, so that I am not left waiting. | Must |
| US-03 | As a user, I want every answer to show its source document, page and rule date, so that I can trust and verify it. | Must |
| US-04 | As a user, I want to open the source document from the answer, so that I can read the original rule. | Should |
| US-05 | As a user, I want the assistant to say clearly when it does not know, so that I am not misled. | Must |
| US-06 | As a user, I want suggested starter questions, so that I know what I can ask. | Should |
| US-07 | As a user, I want to ask a follow-up question in the same conversation, so that I don't have to repeat context. | Could |

### Withdrawal eligibility checker

| ID | User story | Priority |
|---|---|---|
| US-08 | As a user, I want to enter my employment status and dates, so that I can see what PF withdrawal I am eligible for. | Should |
| US-09 | As a user, I want the checker result to show the rule it is based on, so that I can verify it. | Should |

### Trust and safety

| ID | User story | Priority |
|---|---|---|
| US-10 | As a user, I want to see a clear disclaimer, so that I know this is not official advice. | Must |
| US-11 | As the owner, I want off-topic and harmful questions refused, so that the demo is not misused. | Must |
| US-12 | As the owner, I want each user limited to 10 questions a day, so that costs stay under budget. | Must |

## 4. Acceptance criteria (Must stories)

**US-01: Ask a question**
- Given I am on the home page, when I type a question of 3–500 characters and press Enter, then the question is sent and appears in the chat.
- Questions over 500 characters show the message "Please shorten your question."

**US-02: Streaming answer**
- The first words of the answer appear within 3 seconds.
- A loading indicator shows until the first words arrive.

**US-03: Citations**
- Every answer shows at least one source with document title, page number and rule date.
- If newer and older documents disagree, the answer is based on the newer one and says so.

**US-05: "I don't know"**
- When no retrieved document is relevant enough, the answer is: "I couldn't find this in the EPFO documents I have. Please check epfindia.gov.in or contact EPFO." No guessing.

**US-10: Disclaimer**
- A disclaimer is visible on every page: "Not affiliated with EPFO. For information only. Verify on epfindia.gov.in."

**US-11: Guardrails**
- Questions not about EPF/EPS get a polite refusal that suggests what the user can ask.
- Attempts to override instructions (prompt injection) are refused and logged.

**US-12: Rate limit**
- After 10 questions in a day, the user sees: "You've reached today's limit of 10 questions. Please come back tomorrow."
- A global daily cap stops all AI calls if the day's budget is reached; the eligibility checker keeps working.

## 5. Functional requirements

| ID | Requirement |
|---|---|
| FR-01 | Ingest core scheme documents and circulars/FAQs from 2000 onwards from the official EPFO website. |
| FR-02 | Store each document's title, source URL, publication date and content hash. |
| FR-03 | Skip documents that are already ingested (same hash). |
| FR-04 | Extract text from digital and scanned PDFs, including tables. |
| FR-05 | Retrieve relevant passages using hybrid search (keyword + vector) and re-ranking. |
| FR-06 | Rank newer documents higher when passages conflict. |
| FR-07 | Generate answers only from retrieved passages, with citations. |
| FR-08 | Cache answers to repeated questions and serve them without calling the LLM. |
| FR-09 | Run the eligibility checker with fixed rules in code, without the LLM. |

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Performance | First words of an answer in under 3 seconds; full answer in under 10 seconds. |
| Cost | Under ₹300 per month; hard API spending cap; LLM used only for answer generation. |
| Resources | All always-running services together use under 2 GB of RAM on the shared VPS. |
| Availability | Best effort for a demo; automatic restart if a container stops. |
| Security | HTTPS only; API keys kept in environment variables, never in code. |
| Privacy | No login and no personal data stored; question logs contain no IP addresses in plain text. |
| Accessibility | Keyboard navigation and readable contrast (WCAG 2.1 AA basics). |
| Responsive | Works on mobile screens from 360 px wide. |

## 7. Main user flow

1. User opens EPF Mitra and sees the disclaimer and suggested questions.
2. User types a question or taps a suggestion.
3. The answer streams in, followed by its sources and rule dates.
4. User taps a source to open the original document (Should).
5. User asks another question, or opens the eligibility checker.

## 8. Release plan

| Release | Contents | Target |
|---|---|---|
| v0.1 (internal) | Ingestion + Q&A with citations from the command line | Day 6 (11 Nov) |
| v0.5 (internal) | Evaluation baseline + hybrid search | Day 8 (13 Nov) |
| v1.0 (public demo) | Angular UI, FastAPI, guardrails, limits, deployed | Day 14 (19 Nov) |
| v2 | LangGraph agent, pension calculator, Tamil, auto-update of new circulars | After v1 |

## 9. Success metrics

Same as the [BRD](BRD.md#5-success-metrics): accuracy ≥ 0.85, citations on 100% of answers, correct "I don't know" ≥ 90%, under ₹300 per month, 100+ users in the first month.

## 10. Out of scope (v1)

Logging into EPFO, personal account data, filing claims, Tamil and other languages, ESI/NPS, and circulars before 2000.
