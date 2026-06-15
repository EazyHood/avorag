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

## Results (v1 baseline · n=16 · `RERANK_PROVIDER=local` · corpus_version 2026-06-14)
<!-- Paste a screenshot of eval/reports/report.html here -->
| Metric | Value | What it measures (and what it does NOT) |
|---|---|---|
| **Groundedness** | **0.96** | Each claim is backed by the cited chunk. **NOT** agronomic accuracy nor source currency. LLM judge. |
| Answers with a citation | **100%** | **Presence** of a citation, not that the chunk supports the claim (that's `citation_support_rate`). |
| Correct abstention (traps) | **100%** | Over 4 traps (wide 95% CI). |
| Unsupported doses | **0** | Computed by the (now deterministic, product-aware) dose guardrail. |
| Answer rate (real questions) | **83% (10/12; 2 honest abstentions)** | |
| Latency (first hit) | **44,847 ms** with `RERANK_PROVIDER=local` on CPU · **<50 ms** repeated (cache) | Factory default is `none`. |

> The groundedness judge is an LLM (on the local path, `qwen2.5:7b` grades itself: indicative,
> no human validation nor second model). For a commercial claim: independent judge
> (`JUDGE_LLM_PROVIDER`) + human inter-annotator agreement (n≥200). Sample is **small (n=16)**;
> the report shows Wilson 95% CIs. The golden set grew to **n=64** (doses, PHI, tox category,
> mixtures, banned products, adversarial traps).

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
