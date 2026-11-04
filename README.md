# Research Financial Copilot — Agentic AI Proof of Concept for Research Administration

The Research Financial Copilot is an exploratory prototype for helping research administrators review synthetic grant-finance data. It combines a local language model with deterministic Python tools for transaction screening, budget monitoring, forecasts, deadline checks, policy retrieval, and human review.

Research administration often requires connecting individual expenditures to grant budgets, funding periods, reporting deadlines, and supporting policy evidence. An agent can coordinate those checks and assemble a review package, but it should not replace institutional systems, professional judgment, or approval workflows. This project is a proof of concept, not a production-ready university system.

## What is implemented

- Transaction screening for duplicate IDs, missing or invalid fields, unusual amounts, and budget discrepancies.
- Explainable risk scores with configurable screening thresholds and reason codes.
- Grant-specific filtering so an audit for `GRANT-A` excludes `GRANT-B` transactions.
- Budget utilization, remaining-balance, and warning-threshold monitoring.
- Simple historical-average spending forecasts with baseline exhaustion dates.
- Funding-end and reporting-deadline monitoring, including overdue and upcoming items.
- Local retrieval of a limited set of authoritative 2 CFR Part 200 provisions, with source URLs, sections, excerpts, and evidence checks.
- Structured financial review reports combining transaction, budget, forecast, deadline, policy, and review-case information.
- Human-review cases with `pending`, `reviewed`, and `resolved` states, reviewer notes, and review history.
- Multi-step LangGraph workflows in which the model calls these capabilities as tools.

The anomaly screening is deterministic and explainable. This prototype does not implement machine-learning anomaly detection, advanced predictive modeling, comprehensive regulatory coverage, or connections to UC San Diego financial systems. Those are possible future directions, not current capabilities.

## Architecture

- **LangGraph** coordinates the Financial Copilot state machine and tool-calling loop.
- **Ollama** provides a local model backend. The demonstrated configuration uses **Qwen3 8B** (`qwen3:8b`).
- **FastAPI** exposes invocation and streaming endpoints, including `/financial-copilot/stream`.
- **Streamlit** provides the local chat interface and displays tool calls and results.
- **Deterministic Python tools** perform financial calculations, screening, policy matching, deadline logic, report construction, and review-state transitions.

The language model coordinates the workflow and explains returned evidence; it is not asked to invent financial calculations or compliance conclusions. The model backend can be changed through the existing configuration, subject to compatibility and testing.

## Synthetic GRANT-A example

The repository includes synthetic transaction data in `data/sample_transactions.csv`. A verified demonstration for `GRANT-A` produces these values:

| Indicator | Synthetic result |
| --- | ---: |
| Approved budget | $10,000 |
| Spending to date | $5,200 |
| Utilization | 52% |
| Remaining balance | $4,800 |
| Average monthly spending | $1,050 |
| Baseline projected exhaustion date | 2027-04-03 |
| Funding end date | 2026-12-31 |
| Potential unspent funds at funding end | $2,700 |
| Upcoming interim report deadline | 2026-11-15 |
| Flagged GRANT-A transaction | `TX002` |

The exhaustion date is a baseline projection from historical average spending. It is not an assertion of accelerated overspending. The values above are synthetic demonstration results and are not university financial records.

## Local setup and usage

From the repository root, install the existing locked environment:

```sh
uv sync --frozen
source .venv/bin/activate
```

Install Ollama separately using the instructions at <https://ollama.com>. Download the local model and configure the service:

```sh
ollama pull qwen3:8b
export OLLAMA_MODEL=qwen3:8b
export OLLAMA_BASE_URL=http://127.0.0.1:11434
```

Start the FastAPI backend in one terminal:

```sh
source .venv/bin/activate
python src/run_service.py
```

Start the Streamlit frontend in another terminal:

```sh
source .venv/bin/activate
streamlit run src/streamlit_app.py
```

In the interface, select model `ollama` and agent `financial-copilot`. Ask, for example:

> Run a complete synthetic audit for GRANT-A as of 2026-11-03. Use the default synthetic transaction data, screen transactions, check the budget and deadlines, forecast spending, retrieve relevant allowable-cost policy evidence, and prepare a review report. Keep GRANT-B out of the audit and distinguish anomalies from potential compliance issues.

The default agent remains the toolkit's existing `research-assistant`; select `financial-copilot` explicitly for this workflow. No paid API or real financial data is required for the local demonstration.

## Quality assurance and human oversight

The implementation includes safeguards intended to make the prototype reviewable:

- Grant IDs and CSV paths are separate tool arguments. Omitting a path uses the repository's synthetic dataset; a missing supplied path returns a structured error.
- Financial calculations and screening rules run deterministically in Python.
- Transaction results retain source IDs and grant filters.
- Policy results retain section identifiers, exact source URLs, excerpts, matched terms, and evidence status.
- Policy checks distinguish missing evidence, unsupported claims, and ambiguous matches.
- Financial anomalies, potential compliance issues, and confirmed violations are separate concepts. The tools do not establish a regulatory violation.
- Review cases preserve status transitions, reviewer identity, notes, and history.
- Regression tests cover grant filtering, safe file handling, policy evidence, forecasts, deadlines, reports, human review, and multi-tool streaming failures.

These safeguards reduce avoidable workflow errors; they do not guarantee regulatory compliance or eliminate model errors. Human review remains required.

## Limitations

- All transaction and grant records are synthetic.
- The application is not connected to UC San Diego or any other university financial system.
- Policy retrieval uses a small local collection of regulations and may not find every relevant provision. Retrieved evidence still requires administrative and legal review.
- Forecasts use simple historical-average assumptions rather than advanced predictive models.
- Human-review records are prototype data structures, not a production case-management database.
- Institutional deployment would require security controls, permissions, data governance, audit requirements, retention policies, integration testing, and additional validation.

**Optional Voice Features:** The underlying Agent Service Toolkit includes optional speech-to-text (STT) and text-to-speech (TTS) components that are not configured in this prototype. Voice-related initialization warnings may appear in the terminal, but they do not affect the Financial Copilot's text-based workflows, financial analysis, or report generation.

## Attribution and licensing

This project is built on the open-source [Agent Service Toolkit](https://github.com/JoshuaC215/agent-service-toolkit). Its existing repository license is MIT; the original `LICENSE` file is preserved.

The financial screening design was informed by ideas in [Finomaly](https://github.com/Barisaksel/finomaly), and the source-grounded policy retrieval and evidence-validation design was informed by [GovGrant AI](https://github.com/DimasDuran/GovGrant-AI). This prototype does not integrate either project in full and does not claim to reproduce their complete architectures. The Research Financial Copilot's synthetic financial tools, grant-monitoring logic, local policy corpus, report workflow, and Streamlit integration are implemented here for this proof of concept.

Before redistribution beyond a private repository, review the upstream licenses and attribution requirements for each referenced project and confirm that any adapted code or assets are covered. This README does not replace that review.

## Repository sharing notes

Before sharing privately on GitHub, confirm that local-only material is excluded. In particular, do not upload `.env` files, credentials, `privatecredentials` contents, `.venv`, Python caches, checkpoint databases, local model files, logs, temporary artifacts, or personal information. The current ignore rules cover several of these categories, but GitHub's pending changes and tracked-file list should still be reviewed manually before the first commit.

Do not commit or publish secrets merely because the repository is private. Private access reduces exposure but does not replace credential hygiene, collaborator review, or institutional data-approval processes.
