import redis
import time
import os
import signal

r = redis.Redis(
    host=os.getenv("REDIS_HOST", "localhost"),
    port=int(os.getenv("REDIS_PORT", "6379")),
    password=os.getenv("REDIS_PASSWORD") or None,
)

# Graceful shutdown: when Docker sends SIGTERM, finish the current job, then exit
running = True


def shutdown(sig, frame):
    global running
    print("Shutdown signal received, finishing current job...", flush=True)
    running = False


signal.signal(signal.SIGTERM, shutdown)
signal.signal(signal.SIGINT, shutdown)


def process_job(job_id):
    print(f"Processing job {job_id}", flush=True)
    time.sleep(2)  # simulate work
    r.hset(f"job:{job_id}", "status", "completed")
    print(f"Done: {job_id}", flush=True)


print("Worker started, waiting for jobs...", flush=True)
while running:
    try:
        job = r.brpop("job", timeout=5)
        if job:
            _, job_id = job
            process_job(job_id.decode())
    except redis.exceptions.TimeoutError:
        continue  # nothing in the queue this round — completely normal, wait again
    except redis.exceptions.RedisError as e:
        print(f"ERROR: Redis problem, retrying in 3s: {e}", flush=True)
        time.sleep(3)

print("Worker stopped cleanly.", flush=True)
