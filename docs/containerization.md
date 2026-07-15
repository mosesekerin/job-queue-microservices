# Containerization

Three production Dockerfiles. Shared decisions, then per-service specifics.

## Shared decisions

- **Slim official bases** (`python:3.12-slim`, `node:20-slim`) — smaller
  surface, fewer preinstalled programs to exploit.
- **Non-root execution** — `useradd appuser` + `USER appuser` (Python);
  the prebuilt `node` user (Node). Least privilege: an exploited app must not
  be root.
- **Layer-cache ordering** — dependency manifests are COPY'd before source
  code, so the expensive install layer survives code edits. Rule: order layers
  least-changing → most-changing.
- **OS security patching at build time** — every Dockerfile runs
  `apt-get update && apt-get upgrade -y && rm -rf /var/lib/apt/lists/*`
  right after FROM. Added after Trivy found fixable CRITICALs
  (gnutls authentication bypass) inherited from the node:20-slim base
  (Debian 12). Base images are snapshots; fixes published after their build
  date arrive only if the build asks. Corollary: images rot — rebuild on a
  schedule, not only on commits.
- **Healthchecks as machine-readable verdicts** — a command exiting 0/1, never
  prose. These later became load-bearing three times: compose startup ordering,
  the CI integration gate (`--wait`), and the rolling-deploy cutover decision.

## api/Dockerfile — multi-stage

Builder stage creates a venv and installs pinned dependencies; runtime stage
copies only the finished venv. Rationale: discard pip caches and build
leftovers — ship the meal, not the kitchen. `uvicorn --host 0.0.0.0` because
localhost inside a container accepts connections from nobody else.
HEALTHCHECK: HTTP GET against a purpose-built `/health` endpoint.

## worker/Dockerfile — the portless service

No EXPOSE (nothing connects to it), plain `CMD ["python", "worker.py"]`
(the worker is its own engine; FastAPI code needs uvicorn to host it).

**Healthcheck problem:** how to take the pulse of a process with no port —
Docker already detects death for free; the target is the alive-but-stuck
zombie. **Solution:** heartbeat file. The loop touches `/tmp/heartbeat` every
iteration (`brpop(timeout=5)` guarantees a turn at least every ~5s even when
idle); the healthcheck asserts the file is fresher than 15s.

## frontend/Dockerfile — single-stage, deliberately

Multi-stage exists to throw away build waste. This frontend's only build step
is `npm ci --omit=dev`, whose entire output (node_modules) is needed at
runtime — nothing to discard, so a second stage adds complexity for zero
benefit. Patterns are answers to problems, not rituals. (A compiled React/TS
frontend would flip this decision.) Healthcheck uses `node -e` with an HTTP
self-request, since curl does not exist in slim images.

## The operational cycle burned in during this phase

**edit code → rebuild image → replace container.** Images are frozen; editing
source changes nothing inside running containers. Both initial `(unhealthy)`
states in this phase (API /health returning 404; worker heartbeat file never
created) were fixed by exactly this cycle.
