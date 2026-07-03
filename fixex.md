# FIXES.md — Bug Report & Fixes

Broken multi-service application: Frontend (Node.js) → API (FastAPI) → Redis → Worker (Python).
Each issue below lists the file, location, root cause, the fix, and why it matters in production.

---

## api/main.py

### 1. Hardcoded Redis connection
- **Location:** `api/main.py`, line 8 — `r = redis.Redis(host="localhost", port=6379)`
- **Root cause:** The Redis address is baked into the code instead of read from configuration. "localhost" means "this same machine" — true on a laptop, false in containers, where each container is its own isolated host.
- **Fix:** Read connection details from environment variables:
  ```python
  r = redis.Redis(
      host=os.getenv("REDIS_HOST", "localhost"),
      port=int(os.getenv("REDIS_PORT", "6379")),
      password=os.getenv("REDIS_PASSWORD") or None,
  )
  ```
- **Why it matters:** Containerized services resolve dependencies by service name over a shared network, not localhost. Hardcoding guarantees total failure the moment the app is containerized, and forces code changes for every environment (dev/staging/prod). Config belongs outside code (12-factor principle).

### 2. Race condition: job queued before its status exists
- **Location:** `api/main.py`, lines 13–14 (`create_job`)
- **Root cause:** The code runs `lpush` (make job visible to the worker) **before** `hset` (write status "queued"). The worker grabs jobs instantly. In the gap between the two lines, a fast worker can process the job and write "completed" — which the API then overwrites with "queued". Last writer wins.
- **Fix:** Swap the order — status must exist before the job becomes visible:
  ```python
  r.hset(f"job:{job_id}", "status", "queued")
  r.lpush("job", job_id)
  ```
- **Why it matters:** The job would display "queued" forever despite being finished — a permanently wrong state with no error anywhere. Race conditions pass tests and demos, then fail intermittently in production under real load, where they are extremely hard to diagnose. Rule: never make work visible to consumers before its metadata is fully written.

### 3. Configuration file exists but is never read (no Redis auth)
- **Location:** `api/main.py` — `import os` is present but unused; `api/.env` defines `REDIS_PASSWORD` that no code reads
- **Root cause:** The intended bridge between the `.env` file and the code (`os.getenv`) was never written. Redis therefore runs with no authentication at all.
- **Fix:** Covered by fix #1 (read `REDIS_PASSWORD` from the environment) plus configuring Redis itself to require the password (`--requirepass`), delivered in docker-compose.
- **Why it matters:** An unauthenticated Redis reachable by anything on the network can be read, flushed, or poisoned. Even on an internal network, defense in depth requires authentication on data stores.

### 4. No error handling — Redis failure crashes requests with raw 500s
- **Location:** `api/main.py`, both endpoints
- **Root cause:** No try/except around Redis operations. If Redis is down, every request raises an unhandled `ConnectionError`, returning an opaque 500 with a stack trace.
- **Fix:** Catch Redis connection failures and return a deliberate 503 with a clear message; log the underlying error for operators:
  ```python
  from fastapi import HTTPException
  try:
      r.hset(...); r.lpush(...)
  except redis.exceptions.ConnectionError:
      raise HTTPException(status_code=503, detail="queue temporarily unavailable")
  ```
- **Why it matters:** Dependencies fail routinely in production. A service must fail *predictably*: correct status code (503 = temporary, retry later), clean message for clients, detailed log for operators. Raw stack traces leak internals and give clients no guidance.

### 5. "Not found" returned with status 200
- **Location:** `api/main.py`, `get_job` — returns `{"error": "not found"}` with an implicit 200
- **Root cause:** The HTTP status code contradicts the response body. Machines act on status codes, not prose.
- **Fix:** `raise HTTPException(status_code=404, detail="job not found")`
- **Why it matters:** Monitoring, load balancers, retry logic, and client code all key off status codes. "200 OK: not found" silently corrupts every layer that trusts the contract.

---

## worker/worker.py

### 6. Hardcoded Redis connection
- **Location:** `worker/worker.py`, line 6
- **Root cause / Fix / Why:** Identical to issue #1 — read `REDIS_HOST`, `REDIS_PORT`, `REDIS_PASSWORD` from environment variables.

### 7. No error handling — one Redis hiccup kills the worker permanently
- **Location:** `worker/worker.py`, main `while True` loop
- **Root cause:** `brpop` errors (Redis down, Redis not yet started, network blip) are uncaught. The exception escapes the loop and the process exits. There is no retry, no backoff, and no log explaining why.
- **Fix:** Wrap the loop body in try/except; on connection failure, log the error and retry with a delay:
  ```python
  while True:
      try:
          job = r.brpop("job", timeout=5)
          if job:
              _, job_id = job
              process_job(job_id.decode())
      except redis.exceptions.TimeoutError:
          continue  # empty queue this round — normal, wait again
      except redis.exceptions.RedisError as e:
          print(f"Redis problem, retrying in 3s: {e}", flush=True)
          time.sleep(3)
  ```
  Note: `TimeoutError` is *not* a subclass of `ConnectionError` in redis-py — catching only `ConnectionError` leaves a fatal gap (confirmed by live testing: an idle-queue socket timeout crashed the worker). A blocking-pop timeout means "queue was empty", which is routine and handled quietly; all other Redis errors are caught at the family level (`RedisError`), logged, and retried.
- **Why it matters:** Workers are long-lived background processes; resilience to transient dependency failure is their core requirement. A worker that dies silently means jobs pile up in the queue with no visible symptom until users complain. This also fixes the startup-order problem: a worker that retries can start before Redis and simply wait.

### 8. No graceful shutdown — jobs are destroyed on every deploy
- **Location:** `worker/worker.py` — `import signal` present but unused
- **Root cause:** On shutdown, Docker sends SIGTERM ("please finish up"). The worker ignores it, so Docker force-kills it after the grace period — potentially mid-job. Because the job was already popped from the queue, it is lost forever and its status stays "queued" permanently.
- **Fix:** Trap SIGTERM/SIGINT, finish the current job, then exit:
  ```python
  running = True
  def shutdown(sig, frame):
      global running
      running = False
  signal.signal(signal.SIGTERM, shutdown)
  signal.signal(signal.SIGINT, shutdown)

  while running:
      # ... existing loop body ...
  ```
- **Why it matters:** Deploys and restarts are routine, not exceptional. Without graceful shutdown, *every deploy* silently destroys any in-flight job. Combined with pop-before-work semantics, this is guaranteed data loss during normal operations.

---

## frontend/app.js

### 9. Hardcoded API URL
- **Location:** `frontend/app.js`, line 6 — `const API_URL = "http://localhost:8000"`
- **Root cause:** Same class as #1. In a container, localhost:8000 is the frontend container itself — the API is not there.
- **Fix:** `const API_URL = process.env.API_URL || "http://localhost:8000";`
- **Why it matters:** Same as #1 — service addresses are environment-specific configuration.

### 10. Errors swallowed — real cause discarded, wrong status codes returned
- **Location:** `frontend/app.js`, both catch blocks
- **Root cause:** The caught `err` object (containing the actual failure reason) is never logged. Both routes return an identical generic `500 "something went wrong"`, even when the API answered correctly with e.g. 404 — destroying information.
- **Fix:** Log the real error for operators; pass through the upstream status when one exists:
  ```javascript
  } catch (err) {
    console.error("API request failed:", err.message);
    const status = err.response ? err.response.status : 502;
    const detail = err.response ? err.response.data : { error: "api unavailable" };
    res.status(status).json(detail);
  }
  ```
- **Why it matters:** Silent failures are the most expensive kind: the system is broken and nothing says why, where, or since when. Logs exist for operators; status codes exist for machines; both were being thrown away.

### 11. Hardcoded listen port
- **Location:** `frontend/app.js`, last lines — `app.listen(3000, ...)`
- **Root cause:** Ports are configuration.
- **Fix:** `const PORT = process.env.PORT || 3000; app.listen(PORT, ...)`
- **Why it matters:** Port conflicts and per-environment differences shouldn't require code edits or image rebuilds.

---

## Repository level

### 12. Secret committed to version control
- **Location:** `api/.env` — contains `REDIS_PASSWORD=supersecretpassword123`; no `.gitignore` exists
- **Root cause:** Environment files with secrets were committed to a public repository.
- **Fix:**
  1. Remove the file from the repo (`git rm --cached api/.env`).
  2. Add a `.gitignore` that excludes `.env` and `*.env`.
  3. Treat the exposed password as burned — generate a new one; the old one lives forever in git history and clones.
  4. Provide a committed `.env.example` with placeholder values so developers know which variables are required.
- **Why it matters:** Anything ever pushed to a remote must be assumed compromised. Deleting the file in a later commit does not help — history retains it. Secrets belong in untracked local files or a secrets manager, never in git.

### 13. Unpinned Python dependencies — non-reproducible builds
- **Location:** `api/requirements.txt` and `worker/requirements.txt` — packages listed without versions (`fastapi`, `uvicorn`, `redis`)
- **Root cause:** Without pinned versions, pip installs whatever is newest at build time. The same Dockerfile produces different images on different days.
- **Fix:** Pin exact versions in both files:
  ```
  # api/requirements.txt
  fastapi==0.111.0
  uvicorn==0.30.1
  redis==5.0.4

  # worker/requirements.txt
  redis==5.0.4
  ```
- **Why it matters:** Reproducible builds are foundational to production operations: rollbacks, debugging ("what exactly is running?"), and security audits all assume you can rebuild the same artifact. An upstream release should never be able to break your deploy without you changing anything.

### 14. Missing Node lockfile — same problem in disguise
- **Location:** `frontend/package.json` uses caret ranges (`"express": "^4.18.2"` = "4.18.2 or any newer 4.x"); no `package-lock.json` is committed
- **Root cause:** Caret ranges are version *ranges*, not pins. The lockfile that records exact resolved versions was never generated/committed, so every install may resolve differently.
- **Fix:** Run `npm install` locally to generate `package-lock.json`, commit it, and use `npm ci` (not `npm install`) in Docker builds and CI — `npm ci` installs exactly what the lockfile says and fails loudly if it can't.
- **Why it matters:** Identical to #13. The lockfile is the Node ecosystem's pinning mechanism; without it, builds drift silently.

### 15. No documentation
- **Location:** `README.md` — effectively empty
- **Root cause:** No setup instructions, architecture description, or run guide exists.
- **Fix:** Full README covering architecture, service interaction flow, setup from scratch, and how to run — delivered in the documentation stage.
- **Why it matters:** Undocumented systems can only be operated by their author. Onboarding, incident response, and handover all depend on the README being real.
