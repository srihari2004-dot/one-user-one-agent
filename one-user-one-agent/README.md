# One User, One Agent

A runnable, dependency-free Python reference implementation for the OTT Dialect Platform AI Engineering Hiring Challenge. It demonstrates a per-viewer decide → verify → act → judge → measure loop using synthetic data. It is a starting implementation, not a claim that the hidden evaluation pack has been processed.

## What is implemented

- One durable JSON state file per viewer, including evidence facts, decisions, actions, outcomes and learned status.
- Explicit source precedence for dialect: current app setting → profile snapshot → campaign link; disagreements remain visible.
- Goal eligibility for first completed episode within 3 days and first paid plan within 7 days.
- Catalogue dialect and availability filtering; homepage rows require at least three titles.
- Explicit no-action decisions, evidence references, assumptions, checks, confidence reason and latency measurement.
- Idempotent trigger processing, including replayed duplicate triggers.
- Outcome judgment from success signals and an intent-to-treat-style holdout report.
- Mock provider interface; no API key or external model required.
- Tests for duplicate triggers, conflicting dialect sources, provider failure behavior, and corrected goal rules.

## Quick start

Python 3.10+; no third-party runtime packages are required.

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\\Scripts\\activate
pip install -e .
python -m unittest discover -s tests -v
python -m agent.cli --data data --triggers data/triggers.json --state sample_run/viewer_state --out sample_run
```

If running without installation, set the import path:

```bash
PYTHONPATH=src python -m agent.cli --data data --triggers data/triggers.json --state sample_run/viewer_state --out sample_run
PYTHONPATH=src python -m unittest discover -s tests -v
```

The replay writes `decisions.jsonl`, `actions.jsonl`, `outcomes.jsonl`, `latency_report.json`, and `impact_report.md` under `sample_run/`.

## Input files

- `events.json`: synthetic event stream. `received_at` is used for ingestion ordering; `event_time` can be skewed.
- `profiles.json`: synthetic daily snapshot.
- `catalogue.json`: synthetic titles with dialect and availability.
- `goals.json`: goal rules and rule versions.
- `interventions.json`: illustrative intervention constraints.
- `holdout.json`: viewer IDs assigned to the randomized holdout.
- `triggers.json`: replay triggers.

**Important:** the assignment PDF describes a supplied pack of about 5,000 viewers and 1,500 titles, but that data pack was not included with the PDF uploaded in this chat. The included fixtures are small, clearly synthetic examples for a runnable demo; replace them with the evaluator's supplied files and adapt field mappings before scoring.

## Decision contract

Each decision includes `decision_id`, `viewer_id`, trigger details, goal and deadline, action, resolved dialect and conflicts, content IDs, confidence plus reason, inspectable evidence and freshness, assumptions, check results, decision latency, status and a no-action reason.

## Design choices and trust boundaries

1. **Evidence beats model output.** The mock provider can choose from pre-filtered catalogue entries; it cannot assert eligibility or bypass policy checks.
2. **Current app setting wins dialect conflicts.** Profile is a stale fallback, and campaign attribution is last. All conflicts are preserved in the audit record.
3. **Abstention is valid.** Missing goal evidence, missing dialect or fewer than three eligible titles yields no action.
4. **Idempotency.** Processed trigger IDs are persisted per viewer so replays do not repeat an action.
5. **Attribution is conservative.** An observed success is not labelled causal. The impact report compares assigned treatment and holdout groups, not served viewers against all others.
6. **No outbound messaging is enabled.** The demo emits homepage changes only; production push/WhatsApp integrations must implement consent, local-time quiet hours, template policy, and one-message-per-viewer/day caps in an independent verifier.

## Architecture

`trigger → load viewer state → reconcile evidence → select eligible goal → filter catalogue → independent checks → publish/no-op → persist audit state → judge outcomes → compare randomized holdout`.

See [ARCHITECTURE.md](ARCHITECTURE.md), [AI_COLLABORATION.md](AI_COLLABORATION.md), and [KNOWN_LIMITATIONS.md](KNOWN_LIMITATIONS.md).
