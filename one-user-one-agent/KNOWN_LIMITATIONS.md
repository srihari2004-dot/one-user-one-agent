# Known limitations

1. The assignment PDF was provided without the referenced event/profile/catalogue/goal/intervention/pilot/replay data pack. The included fixtures are tiny synthetic examples, not the hidden evaluation dataset.
2. Only two sample goals are implemented. The PDF mentions 12 goals, two underspecified rules, and one unavailable success signal; the missing rule details cannot be resolved without the actual pack/specification. The demo deliberately does not invent them.
3. The profile and event schemas are example schemas and may require adapters for the evaluator's actual files.
4. Persistence uses per-viewer JSON files and is not safe for concurrent writes. Production needs transactional storage and idempotency keys with unique constraints.
5. No real homepage API or messaging provider is integrated. No outbound messages are sent.
6. Local-time quiet hours are documented but cannot be robustly enforced without viewer timezone data; the demo does not implement messaging.
7. Outcome status is a simplified deadline check. A production judge must wait until the deadline has actually passed before declaring failure, handle corrected goal rules and signal definitions with versioned re-evaluation, and distinguish censored data from failure.
8. The holdout report is illustrative; it lacks confidence intervals, stratification, baseline adjustment and robust treatment-assignment validation.
9. The 60-second latency is measured locally and does not prove performance under peak traffic. There is no distributed queue, rate limiter or concurrency/load test.
10. Test coverage is intentionally minimal and should be expanded for late events, stale profile conflicts, injection attempts, quiet hours, consent, message caps, availability windows, corrected goal semantics, storage failure, deadline transitions and high-load replay.
