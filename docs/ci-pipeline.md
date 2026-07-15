# CI/CD Pipeline

Six gates in GitHub Actions, chained with `needs:` so any failure freezes
everything downstream. Each job runs on a fresh disposable runner (runs are
stateless; the memory lives in git).

```
push ──► LINT ──► TEST ──► BUILD ──► SECURITY ──► INTEGRATION ──► DEPLOY
         form     logic    object    contents      assembled       live
                                                    machine        server
```

Each gate examines what the previous gates cannot — proven when the security
gate caught a critical vulnerability that lint, test, and build all waved
through.

## Gate 1 — Lint (flake8, eslint, hadolint)
- Judges form, not function; "it runs" and "it's lint-clean" are different exams.
- First-ever run failed (E302, W291) against a "will pass, it works"
  prediction. Response: adopt formatters (Black, format-on-save) — formatters
  fix the boring 90% automatically; linters guard the meaningful 10%.
- The gate later caught a real regression disguised as pedantry: `F401 Path
  imported but unused` was the smoke from a heartbeat line lost in a
  restructure — without it the worker would run permanently unhealthy.
- Hard gate + tuned rules beats advisory lint (unforced warnings pile up until
  real problems drown). Local mirror of CI:
  `flake8 api/ worker/ --max-line-length=100 --extend-exclude=.venv`
  (the exclude exists because linting a local .venv audits other people's
  libraries against our house rules — thousands of irrelevant findings).

## Gate 2 — Test (pytest + fakeredis + coverage artifact)
- Definition adopted: "we test whether every single thing the program claims
  to be able to do, it can do."
- Real Redis replaced by fakeredis via one repointed variable. Three reasons a
  fake beats the real thing for unit tests: speed, zero setup anywhere, and
  isolation/fresh state per test (no flaky "passes alone, fails together").
- 5 tests: /health contract; job creation writes status AND queues (guards the
  race-condition contract); status read; missing job → 404 (guards FIXES #5
  forever); process_job marks completed (time.sleep monkeypatched — mocking
  applied to time itself).
- Classic failure hit and fixed: pytest hung 28 minutes at "collecting" —
  importing a Python file runs it, and worker.py ended in an infinite loop.
  Fix: `if __name__ == "__main__":` guard; files must be importable without
  side effects.
- Coverage honesty: worker coverage *dropped* 84%→55% after the fix because
  the hang had been executing (and counting) the loop. The number went down
  because the measurement became truthful. Uncovered lines are the
  failure-handling paths fakes never trigger — integration's job.

## Gate 3 — Build (SHA + latest, in-pipeline registry)
- A disposable registry (`registry:2` service container at localhost:5000)
  proves the exact build → tag → push → verify mechanics of production.
- Every image gets two tags: `${{ github.sha }}` (immutable identity — the
  unbreakable link between image and the exact commit; what you roll back to)
  and `latest` (moving convenience alias). Verification step curls the
  registry catalog.

## Gate 4 — Security (Trivy, fail on CRITICAL, ignore-unfixed)
- Target: known CVEs in software we ship but didn't write — an OS's worth of
  packages inside every image. All of our own pinned dependencies scanned clean.
- Failure species logged here:
  - Pipeline-definition failure: a Trivy action version recalled from memory
    didn't exist; nothing of ours was ever examined. Verify versions against
    reality, never memory.
  - Unfixable CRITICALs (perl-base, `fix_deferred`, no fixed version on
    Earth): a gate nobody can satisfy becomes a wall people disable. Policy:
    `ignore-unfixed: true` — block catastrophic holes with a published fix
    (shipping those is your fault); report the rest.
  - Legitimate catch: gnutls CRITICALs (incl. auth bypass) with fixes
    available — node:20-slim rides Debian 12 (older than python:3.12-slim's
    Debian 13). Fix: build-time `apt-get upgrade` in all Dockerfiles.

## Gate 5 — Integration (the assembled machine)
- The production compose file runs verbatim on the runner: generated throwaway
  `.env`, `docker compose up -d --build --wait` (Stage 3 healthchecks now gate
  a CI step), then a real job submitted through the real frontend and polled
  to completion — poll **with a deadline** (10×2s), the antidote to the
  pytest-hang class. `curl -sf` fails on HTTP errors; `if: failure()` dumps
  all container logs; `if: always()` tears down. Passed first try, as
  predicted from the architecture.

## Gate 6 — Deploy
See docs/deployment.md. Runs only on push to main (`if:` guard) — checks are
for proposals, deploys are for accepted truth.

## A taxonomy of failure (all observed in this project)
1. Code-form (lint findings)  2. Code-logic (test failures)
3. Infrastructure noise (transient TLS download corruption — retry, don't
soul-search)  4. Pipeline-definition (broken action reference)
5. Policy tuning (gate correct, rules needed adjusting)
6. Legitimate catches (fixable CVEs; the lost heartbeat)
Diagnosing which layer died — by reading where the run stopped — precedes
every fix.
