from fastapi import FastAPI, HTTPException
import redis
import uuid
import os

app = FastAPI()

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
)

@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/jobs")
def create_job():
    job_id = str(uuid.uuid4())
    try:
        # Status must exist BEFORE the job becomes visible to workers (fix: race condition)
        r.hset(f"job:{job_id}", "status", "queued")
        r.lpush("job", job_id)
    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: Redis unavailable during job creation: {e}", flush=True)
        raise HTTPException(status_code=503, detail="queue temporarily unavailable")
    return {"job_id": job_id}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    try:
        status = r.hget(f"job:{job_id}", "status")
    except redis.exceptions.ConnectionError as e:
        print(f"ERROR: Redis unavailable during status lookup: {e}", flush=True)
        raise HTTPException(status_code=503, detail="queue temporarily unavailable")
    if not status:
        raise HTTPException(status_code=404, detail="job not found")
    return {"job_id": job_id, "status": status.decode()}
