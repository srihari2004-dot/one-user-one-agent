# Architecture note

## Ownership and memory

A single `OneUserOneAgent` decision path owns the goal and plan for a viewer. State is persisted to `viewer_state/<viewer_id>.json`; it contains reconciled facts with provenance, the active goal, processed trigger IDs, decisions, actions and outcomes. The JSON file store is intentionally simple for local replay. A production system should use a transactional database and compare-and-set/version checks to prevent concurrent workers from racing.

## Evidence and source precedence

Dialect precedence is: app setting attached to the current trigger, profile snapshot, campaign link. Conflicts are not erased; the decision includes both the chosen source and conflicting values. Events are ordered by `received_at` rather than trusting potentially skewed device `event_time`. Profile snapshot freshness is carried with the fact. Missing evidence is unknown, not false proof of eligibility.

## Planning and verification

The rule engine selects one eligible goal based on sign-up time, paid status, and observed completion/purchase events. The catalogue filter independently verifies dialect and availability. A homepage action is allowed only when at least three unique titles remain. The model/provider only chooses among already-filtered titles; returned IDs are checked again. An absent goal, unresolved dialect, insufficient catalogue, duplicate trigger, or provider failure yields a recorded no-op.

## Latency and failure recovery

The CLI records per-decision elapsed time and reports whether all decisions are below the 60-second target. The local mock provider avoids network dependency. Provider exceptions are caught and converted into safe abstentions. Production deployments should add bounded timeouts, circuit breakers, queue backpressure, per-decision call counters, and load shedding; a local JSON prototype is not sufficient for a 3x traffic spike or 1,000 concurrent app opens.

## Outcome measurement

Outcomes are judged from the goal's explicit success signal before the goal deadline. This demo reports observed outcomes separately from causal attribution. The impact report compares viewer groups assigned to treatment and randomized holdout (intent-to-treat framing), rather than comparing served viewers with everyone else. Reliable production estimates need complete assignment records, pre-registered metrics, adequate sample size, and confidence intervals.

## Trust boundaries

Catalogue descriptions and model text are untrusted data. They cannot change system policy or authorize outreach. This demo does not send external messages; messaging consent, local timezone, quiet hours, frequency caps and approved-template checks must be independent hard gates before enabling any messaging channel. Synthetic fixtures are not evidence about real users.
