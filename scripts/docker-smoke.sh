#!/usr/bin/env bash
# Docker smoke test (brief §6.1): start the built image and drive the real
# stack end to end — health, a seeded sign-in, opening an opportunity, and a
# PDF export.
#
# Split out of scripts/autopilot-gate.sh so the same steps can be run by hand
# (`make docker-smoke`) and by CI, and so there is one definition of what
# "the image works" means.
#
# Needs a Docker socket, so it cannot run inside the autopilot sandbox. That is
# the deferred half of the split gate; see sandbox/README.md.
#
# Usage: scripts/docker-smoke.sh <image> [container-name]
set -euo pipefail
cd "$(dirname "$0")/.."

IMAGE="${1:?Usage: $0 <image> [container-name]}"
CONTAINER="${2:-opptrail-smoke-$$}"
PORT="${SMOKE_PORT:-8899}"
api="http://127.0.0.1:${PORT}"

jar="$(mktemp)"
cleanup() {
  docker rm -f "$CONTAINER" >/dev/null 2>&1 || true
  rm -f "$jar"
}
trap cleanup EXIT

echo "--- start ---"
docker run -d --rm --name "$CONTAINER" -p "${PORT}:8000" \
  -e OPENAI_API_KEY=smoke-test-unused "$IMAGE" >/dev/null

for _ in $(seq 1 60); do
  curl -fsS "${api}/api/health" >/dev/null 2>&1 && break
  sleep 1
done
# The safe request is also how a client bootstraps its CSRF cookie, exactly as
# the SPA does on page load (backend/app/security.py). Every unsafe call below
# needs that pair, signup included, so this is not just a liveness probe.
curl -fsS -c "$jar" "${api}/api/health" >/dev/null || {
  echo "FAIL: health check never passed"
  docker logs "$CONTAINER" | tail -30
  exit 1
}
echo "health          ok"

csrf="$(awk '$6 == "opptrail_csrf" { print $7 }' "$jar")"
[ -n "$csrf" ] || { echo "FAIL: no CSRF cookie was issued on a safe request"; exit 1; }
echo "csrf cookie     ok"

# The image ships no seed data, so the smoke test creates its own user. That is
# also the only way to prove signup works against the real container.
user="smoke-$(date +%s)@example.com"
curl -fsS -b "$jar" -c "$jar" -X POST "${api}/api/v2/auth/signup" \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: ${csrf}" \
  -d "{\"email\":\"${user}\",\"password\":\"smoke-test-pw-123\",\"name\":\"Smoke Test\"}" >/dev/null
echo "signup          ok"

# Signing in rotates the CSRF token along with the session, so re-read it.
csrf="$(awk '$6 == "opptrail_csrf" { print $7 }' "$jar")"

opp="$(curl -fsS -b "$jar" -X POST "${api}/api/v2/opportunities" \
  -H 'Content-Type: application/json' -H "X-CSRF-Token: ${csrf}" \
  -d '{"name":"Smoke opportunity","account_name":"Acme","stage":"Qualification"}')"
opp_id="$(printf '%s' "$opp" | sed -n 's/.*"id":[ ]*\([0-9]*\).*/\1/p' | head -1)"
[ -n "$opp_id" ] || { echo "FAIL: could not create an opportunity: $opp"; exit 1; }
echo "opportunity     ok (id ${opp_id})"

timeline="$(curl -fsS -b "$jar" "${api}/api/v2/opportunities/${opp_id}/timeline")"
printf '%s' "$timeline" | grep -q "Opportunity created" \
  || { echo "FAIL: the auto-generated timeline entry is missing"; exit 1; }
echo "timeline        ok"

pdf="$(mktemp)"
curl -fsS -b "$jar" "${api}/api/v2/opportunities/${opp_id}/export/pdf" -o "$pdf"
if [ "$(head -c 4 "$pdf")" = "%PDF" ]; then
  echo "pdf export      ok ($(wc -c < "$pdf" | tr -d ' ') bytes, %PDF verified)"
else
  echo "FAIL: export did not return a PDF"; head -c 200 "$pdf"; rm -f "$pdf"; exit 1
fi
rm -f "$pdf"

curl -fsS "${api}/" | grep -qi '<html' \
  || { echo "FAIL: frontend not served from the same origin"; exit 1; }
echo "frontend        ok"

echo "Docker smoke test PASSED for ${IMAGE}."
