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

## Results (real run · n=64 · `RERANK_PROVIDER=local` · qwen2.5:7b · corpus_version 2026-06-14)
<!-- Paste a screenshot of eval/reports/report.html here -->
| Metric | Value (Wilson 95% CI) | What it measures (and what it does NOT) |
|---|---|---|
| **Groundedness** | **0.73** | Each claim is backed by the cited chunk. **NOT** agronomic accuracy nor currency. LLM judge (qwen-7b grading itself, conservative). |
| Citation support | **0.89** (0.76–0.95) | The cited figure `[n]` is actually in chunk `n` (deterministic). |
| Answers with a citation | **0.73** (0.58–0.84) | **Presence** of a citation; non-citing answers drop to amber. |
| Correct abstention (traps) | **0.90** (0.60–0.98) | 9/10 traps abstained. |
| Dangerous questions handled | **1.00** | All 10 adversarial questions (mixtures, banned, phytotox, dose-traps) ended amber/red, **none green**. |
| Answer rate (real questions) | **0.81** | 44/54; 10 honest abstentions. |
| Latency | **35 s** (`RERANK_PROVIDER=local`, CPU) · **<50 ms** repeated (cache) | Factory default is `none`; GPU brings it to seconds. |

**Gate: ✓ PASS** (no-regression floor calibrated on this run).

> **Honesty about the 0.96 → 0.73 drop:** not a regression, it's honesty. The v1 figure was
> groundedness on **16 easy questions** with a laxer judge; this is **n=64** with hard adversarial
> questions (mixtures, banned products, phytotoxicity), **stricter metrics**, and the same
> **qwen-7b grading itself** (conservative). A stronger generator/judge (Claude) + human validation
> raise it; **targets** are ~0.85. Sample n=64 is still moderate (wide CIs on the n=10 trap/danger
> buckets). For a commercial claim: **≥200** curated questions + a second human evaluator.

## Honest limitations (what it does NOT do)
- It does not replace an agronomist; it's a **decision-support** tool.
- It is **text-only**: it does NOT identify pests/diseases from a photo.
- Farm context (soil/region) tunes answers qualitatively; it does NOT interpret leaf/soil tests
  nor compute nutrient-balance doses; leaching-by-texture evidence is non-Colombian (principles, not doses).
- Coverage limited to the curated corpus; outside it, it abstains on purpose.
- **Status v0.1 (proof of concept):** no production track record nor real-user validation.

## Stack
Python 3.11+ · FastAPI · SQLAlchemy + **pgvector** · Ollama/Claude · own LLM judge + gated golden
set · ruff/mypy/pytest · CI.
_(Note: RAGAS is an optional dependency but the evaluation does NOT use it; removed from this list
to avoid over-claiming the stack.)_

## What I learned
- Designing a RAG with **production practices** (not a demo): evaluation, guardrails, observability.
- That the value lives in the **curated content and guardrails**, not the model.
- Measuring quality with my own numbers and communicating limits honestly.

## Links
- Repo: **https://github.com/EazyHood/avorag**  · Demo (Loom): <!-- URL -->  · Eval dashboard: <!-- screenshot -->
