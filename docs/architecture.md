# Architecture

## System overview

A job-processing pipeline of four services. The frontend and API never block on
work; jobs are processed asynchronously by a worker through a Redis queue.

| Service  | Tech            | Role                                              | Listens on |
|----------|-----------------|---------------------------------------------------|------------|
| frontend | Node.js/Express | Serves the UI, proxies requests to the API        | 3000 (container) |
| api      | Python/FastAPI  | Creates jobs, writes status, answers status reads | 8000       |
| redis    | Redis 7         | Job queue (list) + status board (hashes)          | 6379 (internal only) |
| worker   | Python          | Pulls jobs, processes, marks completed            | — (no port) |

```
 Browser ──► Frontend (3000) ──► API (8000) ──► Redis ◄── Worker
                                    ▲          queue│
                                    │       + status│
                                    │               │
                                    └ status reads--│
```

## The journey of one job

1. Browser POSTs `/submit`; frontend forwards to `POST /jobs` on the API.
2. API generates a UUID job id, writes `status=queued` to the status hash
   **first**, then pushes the id onto the queue (order is load-bearing — see
   FIXES.md #2), and returns the id immediately (asynchronous by design).
3. Worker, blocked on `brpop`, receives the id, simulates work (2s), writes
   `status=completed`.
4. Browser polls `/status/{id}` → frontend → `GET /jobs/{id}` → status hash.

## Key design decisions

- **API and worker never talk directly** — only through Redis. Workers can be
  scaled to N copies without touching the API (demonstrated during rolling
  deploys, where two workers briefly drain one queue).
- **A port belongs to the listener.** Outgoing connections need no declaration;
  the worker exposes nothing because nothing ever connects to it.
- **One image per service, never one image for all.** Independent failure,
  independent scaling, independent deployability — demonstrated in practice by
  rebuilding api+worker while frontend and redis ran untouched for hours.
- **Config outside code.** All host names, ports, and credentials come from
  environment variables with local-friendly fallbacks; the same code runs
  unmodified on a laptop, in CI, and in production.
- **Loud failure over silent failure.** Every service logs real causes and
  returns honest status codes (503 queue unavailable, 502 api unreachable,
  404 unknown job).
- **Liveness over readiness — deliberately.** Healthchecks answer "is my
  process alive and looping?", not "are my dependencies up?". Deep checks would
  cascade a Redis outage into restart churn that fixes nothing. Consequence
  observed live: during a Redis outage every service stays healthy while only
  the requests that need Redis fail politely (graceful degradation).

## Failure points identified and addressed

| Failure | Handling |
|---|---|
| Redis down at startup | Worker retry loop; compose health-gated start order |
| Redis down mid-flight | API returns 503; worker retries every 3s; self-heals on return |
| Worker crash (SIGKILL/OOM) | `restart: unless-stopped` resurrects it (verified in production) |
| Deploy kills worker mid-job | SIGTERM handler finishes current job first |
| Alive-but-stuck ("zombie") worker | Heartbeat-file healthcheck detects staleness |
| Broken new release | Rolling deploy: old container never stops until new proves healthy |

## Known limitations (explicitly accepted, documented)

- A worker killed with SIGKILL mid-job loses that job (popped before
  processing). Durable handling requires ack-after-processing queue semantics —
  see Planned Future Work.
- The frontend swap during deploys has a ~1–2s blip (host port binding);
  true zero-downtime needs a reverse proxy in front.
