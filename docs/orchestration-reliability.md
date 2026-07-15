# Orchestration & Reliability

## docker-compose.yml — the declarative stack

One file replaces the hand-typed network + four `docker run` commands
(imperative → declarative: describe the end state, let the tool derive steps).

Key properties, each verified live:

- **Service names are network addresses.** Compose DNS resolves `redis` and
  `api` on the shared `appnet` bridge; names survive container replacement.
- **Redis is not exposed externally.** No `ports:` mapping — reachable only
  from inside the network. The frontend's published port is the single
  deliberate door into the system.
- **Redis requires authentication.** `--requirepass "${REDIS_PASSWORD}"`;
  verified both ways (`NOAUTH` without the password, `PONG` with it).
- **Health-gated startup order.** `depends_on` with
  `condition: service_healthy` — bare depends_on orders *starting*, not
  *readiness*. Observed startup: redis Healthy 12.4s → worker/api released in
  parallel → api Healthy 32.8s → frontend 33.1s. Nobody human sequenced it.
- **Resource limits** (0.5 CPU / 256M per service) — a leaking service gets
  throttled or killed alone instead of starving the machine.
- **`restart: unless-stopped`** on all services — fight crashes, respect
  humans (see semantics below).
- **Environment-driven config** — `.env` auto-read beside the yml;
  `"${FRONTEND_PORT:-3000}:3000"` lets production publish on 3001 (Grafana
  owns 3000 on the shared host) with zero code change.

## Chaos drills — reliability proven, not assumed

### Drill 1: dependency outage (`docker compose stop redis`)
Prediction: api/worker would fail and go unhealthy. Reality: everything stayed
up and healthy; only Redis-dependent requests failed (politely, 503); on
`start redis`, the worker's retry loop reconnected unaided. Concepts extracted:
container failure ≠ service unhealthiness ≠ request failure; health is exactly
the healthcheck's verdict; graceful degradation is the microservice payoff.

### Drill 2: crash without a restart policy (`docker compose kill worker`)
Worker `Exited (137)` and stayed dead — the gap the drill was built to expose.
Exit-code literacy: 137 = 128 + signal 9 (SIGKILL) — in the wild, usually the
OOM killer. stop/kill/rm ladder corrected: kill does not destroy the container
(`ps -a` shows it, restartable). Queued jobs are parked, not lost; the true
SIGKILL casualty is a job already popped and mid-processing.

### Drill 3: restart semantics — a corrected mental model
After adding `unless-stopped`, `docker compose kill` STILL did not trigger a
restart — contradicting the mentor's explanation. Corrected model, proven by
terminal: restart policies key off **who caused the death**, not violence.
Any stop or kill issued through Docker is recorded as operator intent and
respected. Honest crash simulation kills the process behind Docker's back:
`sudo kill -9 $(docker inspect -f '{{.State.Pid}}' <container>)` → policy
fires → resurrection verified. Restart fingerprint: CREATED stays old, STATUS
resets young. Meta-lesson: when an experiment contradicts the model, suspect
the model — and check what the test actually measures.

### Production validation (unplanned)
Weeks later on EC2, a real transient `redis.exceptions.TimeoutError` escaped
the (too-narrow) exception net and killed the worker; `unless-stopped`
resurrected it automatically (fingerprint observed in `docker compose ps`).
Root cause fixed by widening to `RedisError` (FIXES.md #16). Defense in depth,
witnessed live.

## Operational rules distilled

- Rebuild vs recreate vs no-op: code/Dockerfile changed → `up -d --build`;
  compose config changed → `up -d` recreates affected containers; nothing
  changed → `up -d` is idempotent.
- `docker compose ps` hides stopped containers; `-a` shows them.
- Verify configuration on the running object
  (`docker inspect -f '{{.HostConfig.RestartPolicy.Name}}' ...`), don't assume.
- Timing numbers (healthcheck grace periods, deadlines) are local measurements,
  not laws — a deadline tuned on fast hardware can fail honest software on
  slow hardware ("broken in CI, fine locally").
