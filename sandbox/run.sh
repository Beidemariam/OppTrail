#!/usr/bin/env bash
# Host-side launcher for the autopilot sandbox.
#
# This script is the containment boundary. What the agent can reach is decided
# here, by what is mounted -- not by instructions in the brief.
#
# Usage:
#   sandbox/run.sh build            Build (or rebuild) the sandbox image
#   sandbox/run.sh login            One-time interactive Claude Code sign-in
#   sandbox/run.sh verify           Print what the sandbox can and cannot reach
#   sandbox/run.sh shell            Interactive shell inside the sandbox
#   sandbox/run.sh autopilot [...]  Run scripts/autopilot.sh inside the sandbox
#
# Environment:
#   MAX_RUNS, MAX_TURNS   Passed through to scripts/autopilot.sh
#   ANTHROPIC_API_KEY     Optional; if set, used instead of the stored login
#   CPUS, MEMORY          Resource caps (default 4 CPUs, 8g)
set -euo pipefail
cd "$(dirname "$0")/.."

REPO_ROOT="$PWD"
IMAGE="opptrail-autopilot-sandbox"
CLAUDE_VOLUME="opptrail-autopilot-claude"      # agent's own Claude home, not yours
LOG_DIR="${REPO_ROOT}/../opptrail-autopilot-logs"
CPUS="${CPUS:-4}"
MEMORY="${MEMORY:-8g}"

mkdir -p "$LOG_DIR"

# Deliberately NOT mounted, and each omission is load bearing:
#   ~/.ssh                  -> push and force-push fail for lack of credentials,
#                              which is brief 9 enforced by absence
#   ~/.claude               -> your other projects' history and sessions stay out
#   /var/run/docker.sock    -> socket access is root-equivalent on the host and
#                              would make the sandbox decorative (README.md)
#   $HOME, /tmp, anything else on the host
common_args=(
  --rm
  --name "opptrail-autopilot-$$"
  --hostname autopilot-sandbox
  --cpus "$CPUS"
  --memory "$MEMORY"
  --pids-limit 512
  --volume "${REPO_ROOT}:/work/repo"
  --volume "${LOG_DIR}:/work/opptrail-autopilot-logs"
  --volume "${CLAUDE_VOLUME}:/home/node/.claude"
  # Overlays, so a container `npm ci` or `next build` cannot replace the host's
  # native modules (@swc, sharp) or its built output with Linux equivalents.
  --volume "opptrail-autopilot-node-modules:/work/repo/frontend/node_modules"
  --volume "opptrail-autopilot-next:/work/repo/frontend/.next"
  --volume "opptrail-autopilot-out:/work/repo/frontend/out"
  --workdir /work/repo
  --env "MAX_RUNS=${MAX_RUNS:-40}"
  --env "MAX_TURNS=${MAX_TURNS:-250}"
  --env TERM=xterm-256color
  # The bind-mounted .git/config carries your identity and outranks the image's
  # --global config, so autopilot commits would be attributed to you. These
  # override both without modifying the shared .git/config.
  --env "GIT_AUTHOR_NAME=OppTrail Autopilot"
  --env "GIT_AUTHOR_EMAIL=autopilot@localhost"
  --env "GIT_COMMITTER_NAME=OppTrail Autopilot"
  --env "GIT_COMMITTER_EMAIL=autopilot@localhost"
)
[ -n "${ANTHROPIC_API_KEY:-}" ] && common_args+=(--env "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}")

image_exists() { docker image inspect "$IMAGE" >/dev/null 2>&1; }

build() {
  # Context is sandbox/ only -- the repo arrives at runtime via bind mount, so
  # the build never copies source and stays fast.
  docker build \
    --build-arg "UID=$(id -u)" \
    --build-arg "GID=$(id -g)" \
    --tag "$IMAGE" \
    "${REPO_ROOT}/sandbox"
}

ensure_image() { image_exists || { echo "Image missing; building."; build; }; }

case "${1:-}" in
  build)
    build
    ;;

  login)
    ensure_image
    echo "Signing in inside the sandbox. Credentials persist in the '${CLAUDE_VOLUME}'"
    echo "Docker volume and are separate from your host login."
    docker run -it "${common_args[@]}" "$IMAGE" claude /login
    ;;

  verify)
    ensure_image
    docker run -i "${common_args[@]}" "$IMAGE" bash -s <<'PROBE'
set -u
echo "=== identity ==="
printf 'user            %s (uid %s)\n' "$(id -un)" "$(id -u)"
# git var reports the effective identity, which env vars control; git config
# would only show the bind-mounted .git/config value and mislead.
printf 'commit author   %s\n' "$(git var GIT_AUTHOR_IDENT | sed 's/ [0-9]* [+-][0-9]*$//')"
echo
echo "=== toolchain ==="
for c in node npm python3 uv git make claude rg; do
  printf '%-10s %s\n' "$c" "$($c --version 2>&1 | head -1 || echo MISSING)"
done
printf '%-10s %s\n' "uv python" "$(uv run --python 3.13 python -c 'import sys; print(sys.version.split()[0])' 2>&1 | tail -1)"
echo
echo "=== repo is writable, and is the only host path present ==="
printf 'repo            %s\n' "$([ -w /work/repo/.git ] && echo writable || echo 'NOT WRITABLE')"
printf 'logs            %s\n' "$([ -w /work/opptrail-autopilot-logs ] && echo writable || echo 'NOT WRITABLE')"
echo
echo "=== containment (all of these must be denied) ==="
printf 'docker socket   %s\n' "$([ -S /var/run/docker.sock ] && echo 'REACHABLE - ISOLATION BROKEN' || echo 'absent (ok)')"
printf 'ssh keys        %s\n' "$([ -e /root/.ssh ] || [ -e /home/node/.ssh ] && echo 'PRESENT - ISOLATION BROKEN' || echo 'absent (ok)')"
printf 'host home       %s\n' "$([ -e /Users ] && echo 'MOUNTED - ISOLATION BROKEN' || echo 'absent (ok)')"
push_out="$(cd /work/repo && git push --dry-run origin HEAD 2>&1 || true)"
if printf '%s' "$push_out" | grep -qiE 'cannot run ssh|unable to fork|permission denied|could not read|publickey|host key'; then
  printf 'git push        %s\n' "blocked: $(printf '%s' "$push_out" | head -1) (ok)"
else
  printf 'git push        %s\n' "NOT BLOCKED - ISOLATION BROKEN: $(printf '%s' "$push_out" | head -1)"
fi
echo
echo "=== commit-to-main guard ==="
cd /work/repo
git stash list >/dev/null 2>&1
if git commit --allow-empty -m 'sandbox guard probe' >/dev/null 2>&1; then
  echo "guard           FAILED - an empty commit landed on $(git rev-parse --abbrev-ref HEAD)"
  git reset --hard HEAD~1 >/dev/null 2>&1
else
  echo "guard           refused a commit on $(git rev-parse --abbrev-ref HEAD) (ok)"
fi
PROBE
    ;;

  shell)
    ensure_image
    docker run -it "${common_args[@]}" "$IMAGE" bash
    ;;

  autopilot)
    ensure_image
    shift || true
    # No -t: the agent's session must stay non-interactive so the terminal guard
    # in scripts/autopilot-accept.sh cannot be satisfied from inside here.
    docker run -i "${common_args[@]}" "$IMAGE" scripts/autopilot.sh "$@"
    ;;

  *)
    sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
