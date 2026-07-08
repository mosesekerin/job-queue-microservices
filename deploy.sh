#!/usr/bin/env bash
set -euo pipefail

TIMEOUT=60

wait_healthy() {
  local cid=$1 name=$2 waited=0
  while true; do
    local status
    status=$(docker inspect -f '{{.State.Health.Status}}' "$cid")
    if [ "$status" = "healthy" ]; then
      echo "$name: healthy after ${waited}s"
      return 0
    fi
    if [ "$waited" -ge "$TIMEOUT" ]; then
      echo "$name: NOT healthy after ${TIMEOUT}s"
      return 1
    fi
    sleep 5
    waited=$((waited + 5))
  done
}

rolling_update() {
  local svc=$1
  echo "=== Rolling update: $svc ==="
  local old_id new_id
  old_id=$(docker compose ps -q "$svc")

  # 1. START the new container ALONGSIDE the old (old keeps serving)
  docker compose up -d --no-deps --no-recreate --scale "$svc=2" "$svc"
  new_id=$(docker compose ps -q "$svc" | grep -v "$old_id")

  # 2. WAIT for the new one to prove itself
  if ! wait_healthy "$new_id" "$svc (new)"; then
    # 3a. ABORT: kill the unproven newcomer; the old never stopped serving
    echo "$svc: aborting deploy, removing new container"
    docker rm -f "$new_id"
    exit 1
  fi

  # 3b. CUTOVER: new is proven -> retire the old peacefully
  docker stop "$old_id" && docker rm "$old_id"
  echo "$svc: rollover complete"
}

echo "Building images from current code..."
docker compose build

rolling_update api
rolling_update worker

# Frontend binds a host port - two copies can't share one door.
# So: prove the new image with a CANARY (no port), then fast-recreate.
echo "=== Frontend: canary verification, then swap ==="
docker run -d --name frontend-canary --network appnet \
  -e API_URL=http://api:8000 microapp-frontend

if ! wait_healthy frontend-canary "frontend (canary)"; then
  docker rm -f frontend-canary
  exit 1
fi
docker rm -f frontend-canary
docker compose up -d --no-deps frontend
echo "frontend: swapped"

echo "=== Deploy complete ==="
docker compose ps
