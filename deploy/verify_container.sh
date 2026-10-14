#!/bin/sh
# Local Linux acceptance only. Requires an already installed Docker daemon.
set -eu
IMAGE=${IMAGE:-lighttry-cpu:2026.10.14-cpu.1}
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
RUN=${RUN:-/var/tmp/lighttry-container-acceptance}
[ ! -e "$RUN" ] || { echo 'Fresh private RUN directory required' >&2; exit 2; }
mkdir -p "$RUN/data" "$RUN/acceptance"
chmod 700 "$RUN" "$RUN/data"
chown 10001:10001 "$RUN/data"
cp "$ROOT/deploy/container_fixture.py" "$ROOT/project/tests/inference_fixture.py" "$RUN/acceptance/"
chmod -R a+rX "$RUN/acceptance"
docker run --rm --network none -v "$RUN/data:/var/lib/lighttry" "$IMAGE" python -B start.py --service --init-account --account-output /var/lib/lighttry/login.txt
NAME=lighttry-cpu-acceptance
# Fail rather than remove an unrelated existing container.
if docker container inspect "$NAME" >/dev/null 2>&1; then echo 'Acceptance name already in use' >&2; exit 2; fi
cleanup() { docker stop -t 10 "$NAME" >/dev/null 2>&1 || true; docker rm "$NAME" >/dev/null 2>&1 || true; }
trap cleanup EXIT HUP INT TERM
common_run() {
 docker run -d --name "$NAME" --read-only --cap-drop ALL --security-opt no-new-privileges --pids-limit 128 --memory 512m \
  -p 127.0.0.1:18080:8080 -v "$RUN/data:/var/lib/lighttry" \
  -e LIGHTTRY_PUBLIC_ORIGIN=http://localhost:8080 -e LIGHTTRY_ACCOUNTS_FILE=/var/lib/lighttry/auth/accounts.json "$@"
}
common_run -v "$RUN/acceptance:/acceptance:ro" "$IMAGE" python -B /acceptance/container_fixture.py
PYTHON=${PYTHON:-python3}
"$PYTHON" "$ROOT/deploy/container_acceptance.py" create "$RUN/data/login.txt" "$RUN/state.json"
docker logs "$NAME"
cleanup
common_run "$IMAGE"
"$PYTHON" "$ROOT/deploy/container_acceptance.py" restore "$RUN/data/login.txt" "$RUN/state.json"
docker restart -t 10 "$NAME"
"$PYTHON" "$ROOT/deploy/container_acceptance.py" restart "$RUN/data/login.txt" "$RUN/state.json"
docker exec "$NAME" python -c 'import importlib.metadata as m,json; print(json.dumps({n:m.version(n) for n in ("waitress","numpy","Pillow","PyYAML")}))'
docker logs "$NAME"
docker image inspect "$IMAGE" --format '{{json .}}' > "$RUN/image.json"
echo 'Actual CPU container acceptance PASS; synthetic result only; no GPU/cloud acceptance.'
