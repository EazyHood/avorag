# Case study — AvoRAG (Hass Advisor)

> **Spanish-language conversational agronomic assistant (RAG), commercially neutral and
> source-citing, specialized in export-grade Hass avocado.**
> _Built by an agronomy engineer to demonstrate applied AI with real domain judgment._

> ℹ️ **Template:** replace the `{{...}}` placeholders with your real numbers after running
> `uv run avorag eval` (output in `eval/reports/report.html`). Never present third-party figures as your own.

## The problem
Export-grade Hass avocado in Colombia faces two pressures at once:
- **Extension gap:** too few agronomists for hundreds of supplier farms; management advice
  arrives late and inconsistent.
- **Border rejections:** a mismanaged pest or a chemical residue above the MRL can cost a
  **whole container** in the EU/US.

Generic AI assistants **hallucinate dosages** and don't cite sources — unacceptable when a
wrong dose ruins a crop or a certification.

## The solution
AvoRAG answers Hass management questions **only from a curated official corpus**
(Agrosavia, ICA, Corpohass), **citing the source of every claim**, **blocking any dosage not
traceable to a registered label**, and **abstaining when it doesn't know** instead of inventing.

## Why me
The hard part isn't the LLM (AI does that alone): it's **encoding agronomic judgment** —
which sources are authoritative, which dose thresholds are valid, what must always go to a
licensed professional. That's my contribution as an agronomist, and the product's moat.

## Key design decisions
- **Commercial neutrality:** sells no inputs; its only loyalty is the official source.
- **Source-level citations** (name + page): traceability that a B2B buyer demands.
- **Dose guardrail:** a dosage figure is accepted only if it appears, with its unit, in a
  cited source; otherwise it's flagged 🔴 → human review.
- **Honest abstention** as a feature: distinguishes "no info", "out of domain", "other crop".
- **Traffic-light 🟢🟡🔴** + **human-in-the-loop** for high-risk (toxicity class I/II) advice.
- **Evaluation as a gate:** a verified golden set measures quality and blocks regressions.

## Architecture (overview)
**Hybrid** retrieval (dense `pgvector` + Spanish lexical FTS) → **RRF** fusion →
**reranking** → evidence-first prompt → LLM → **guardrails** → traffic light → audit log.
Providers swappable by config (free local via Ollama, or Claude for the sales demo). Details
in [`ARCHITECTURE.md`](ARCHITECTURE.md).

## Results (measured on my golden set of 16 questions)
<!-- Paste a screenshot of eval/reports/report.html here -->
| Metric | Value |
|---|---|
| Mean faithfulness | **0.96** |
| Citation rate (answered) | **100%** |
| Correct abstention (traps) | **100%** |
| High-severity dose hallucinations | **0** |
| Answer rate (real questions) | **83% (10/12; 2 honest abstentions)** |
| Mean latency | **44,847 ms** (reranker on CPU) |

> How I got there: curated corpus + Contextual Retrieval + hybrid search + reranking + dose
> guardrail. _(If I compare models/configs, I add a before/after table.)_

## Honest limitations (what it does NOT do)
- It does not replace an agronomist; it's a **decision-support** tool.
- Photo diagnosis would be a hint, not a verdict (not implemented in this version).
- Dose unit equivalence (kg↔g) is a pending guardrail improvement.
- Coverage limited to the curated corpus; outside it, it abstains on purpose.

## Stack
Python 3.12 · FastAPI · SQLAlchemy + **pgvector** · Ollama/Claude · RAGAS · ruff/mypy/pytest · CI.

## What I learned
- Designing a **production** RAG (not a demo): evaluation, guardrails, observability.
- That the value lives in the **curated content and guardrails**, not the model.
- Measuring quality with my own numbers and communicating limits honestly.

## Links
- Repo: **https://github.com/EazyHood/avorag**  · Demo (Loom): <!-- URL -->  · Eval dashboard: <!-- screenshot -->
