#!/usr/bin/env bash
# Host-side launcher for the autopilot sandbox.
#
# This script is the containment boundary. What the agent can reach is decided
# here, by what is mounted and what the network permits -- not by instructions
# in the brief.
#
# Usage:
#   sandbox/run.sh build            Build (or rebuild) the sandbox image
#   sandbox/run.sh login            One-time interactive Claude Code sign-in
#   sandbox/run.sh verify           Print what the sandbox can and cannot reach
#   sandbox/run.sh proxy-log        Show what egress was requested and allowed
#   sandbox/run.sh shell            Interactive shell inside the sandbox
#   sandbox/run.sh autopilot [...]  Run scripts/autopilot.sh inside the sandbox
#
# Environment:
#   MAX_RUNS, MAX_TURNS   Passed through to scripts/autopilot.sh
#   MODEL                 Model for the agent session (opus/sonnet/haiku or a
#                         full model id). Unset uses the CLI default.
#   ANTHROPIC_API_KEY     Optional; if set, used instead of the stored login
#   CPUS, MEMORY          Resource caps (default 4 CPUs, 8g)
set -euo pipefail
cd "$(dirname "$0")/.."

REPO_ROOT="$PWD"
IMAGE="opptrail-autopilot-sandbox"
PROXY_IMAGE="opptrail-autopilot-proxy"
PROXY_NAME="opptrail-autopilot-proxy"
NETWORK="opptrail-autopilot-net"               # --internal: no route off the host
HOME_VOLUME="opptrail-autopilot-home"          # agent's own home, not yours
LOG_DIR="${REPO_ROOT}/../opptrail-autopilot-logs"
CPUS="${CPUS:-4}"
MEMORY="${MEMORY:-8g}"

mkdir -p "$LOG_DIR"

# The sandbox has no route to the internet. It sits alone on an internal Docker
# network whose only other member is the egress proxy, which forwards solely to
# the hostnames in sandbox/proxy/allowlist.conf. An agent trying to reach
# anything else has no path, rather than an instruction not to.
ensure_network() {
  docker network inspect "$NETWORK" >/dev/null 2>&1 \
    || docker network create --internal "$NETWORK" >/dev/null
}

ensure_proxy() {
  docker image inspect "$PROXY_IMAGE" >/dev/null 2>&1 \
    || docker build --tag "$PROXY_IMAGE" "${REPO_ROOT}/sandbox/proxy"
  if ! docker ps --filter "name=^${PROXY_NAME}$" --filter status=running -q | grep -q .; then
    docker rm -f "$PROXY_NAME" >/dev/null 2>&1 || true
    # Starts on the default bridge, which is where its own egress comes from,
    # then joins the internal network as "proxy" for the sandbox to reach.
    docker run -d --name "$PROXY_NAME" --network bridge \
      --security-opt no-new-privileges \
      --memory 256m --pids-limit 128 \
      "$PROXY_IMAGE" >/dev/null
    docker network connect --alias proxy "$NETWORK" "$PROXY_NAME"
    for _ in $(seq 1 30); do
      docker logs "$PROXY_NAME" 2>&1 | grep -q "Accepting HTTP" && break
      sleep 1
    done
  fi
}

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
  --shm-size 1g
  # No route off the host except through the allowlisting proxy.
  --network "$NETWORK"
  --env "HTTP_PROXY=http://proxy:3128"
  --env "HTTPS_PROXY=http://proxy:3128"
  --env "http_proxy=http://proxy:3128"
  --env "https_proxy=http://proxy:3128"
  --env "NO_PROXY=localhost,127.0.0.1"
  --env "no_proxy=localhost,127.0.0.1"
  # No capabilities, and no way to acquire any: setuid binaries cannot elevate.
  --cap-drop ALL
  --security-opt no-new-privileges
  # Root filesystem is immutable; every writable path is named below, so the
  # agent cannot alter its own toolchain, the hook, or the system git config.
  --read-only
  --tmpfs /tmp:rw,nosuid,nodev,size=2g
  --tmpfs /run:rw,nosuid,nodev,size=64m
  --volume "${REPO_ROOT}:/work/repo"
  --volume "${LOG_DIR}:/work/opptrail-autopilot-logs"
  --volume "${HOME_VOLUME}:/home/node"
  --volume "opptrail-autopilot-venv:/work/venv"
  --volume "opptrail-autopilot-pw:/work/pw-browsers"
  --workdir /work/repo
  --env "MAX_RUNS=${MAX_RUNS:-40}"
  --env "MAX_TURNS=${MAX_TURNS:-250}"
  --env TERM=xterm-256color
  # The bind-mounted .git/config carries your identity and outranks the image's
  # system config, so autopilot commits would be attributed to you. These
  # override both without modifying the shared .git/config.
  --env "GIT_AUTHOR_NAME=OppTrail Autopilot"
  --env "GIT_AUTHOR_EMAIL=autopilot@localhost"
  --env "GIT_COMMITTER_NAME=OppTrail Autopilot"
  --env "GIT_COMMITTER_EMAIL=autopilot@localhost"
)
[ -n "${ANTHROPIC_API_KEY:-}" ] && common_args+=(--env "ANTHROPIC_API_KEY=${ANTHROPIC_API_KEY}")
[ -n "${MODEL:-}" ] && common_args+=(--env "MODEL=${MODEL}")

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

ensure_image() {
  image_exists || { echo "Image missing; building."; build; }
  ensure_network
  ensure_proxy
}

case "${1:-}" in
  build)
    build
    ;;

  login)
    # docker run -it needs a real terminal. Running this through a wrapper that
    # pipes stdin (Claude Code's ! prefix, CI, `| tee`) fails with an opaque
    # Docker error, so say what to do instead.
    if [ ! -t 0 ] || [ ! -t 1 ]; then
      echo "sandbox/run.sh login needs a real terminal for the sign-in prompts." >&2
      echo >&2
      echo "Open a terminal window and run:" >&2
      echo "  cd ${REPO_ROOT} && sandbox/run.sh login" >&2
      echo >&2
      echo "Or skip the interactive login by exporting an API key instead:" >&2
      echo "  ANTHROPIC_API_KEY=sk-... sandbox/run.sh autopilot" >&2
      exit 1
    fi
    ensure_image
    echo "Signing in inside the sandbox. Credentials persist in the '${HOME_VOLUME}'"
    echo "Docker volume and are separate from your host login."
    echo
    echo "Claude Code will open below. Type:  /login"
    echo "Then follow the prompts, and /exit when it reports you are signed in."
    echo "The container has no browser, so it will print a URL to open on the host."
    echo
    docker run -it "${common_args[@]}" "$IMAGE" claude
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
echo
echo "=== repo is writable, and is the only host path present ==="
printf 'repo            %s\n' "$([ -w /work/repo/.git ] && echo writable || echo 'NOT WRITABLE')"
printf 'logs            %s\n' "$([ -w /work/opptrail-autopilot-logs ] && echo writable || echo 'NOT WRITABLE')"
echo
echo "=== privilege (no path to root) ==="
printf 'sudo            %s\n' "$(command -v sudo >/dev/null 2>&1 && echo 'PRESENT - ESCALATION POSSIBLE' || echo 'not installed (ok)')"
# </dev/null matters: su reads a password from stdin, which here is the probe
# script itself, and would swallow every line after this one.
printf 'su              %s\n' "$(su root -c true </dev/null 2>&1 | grep -qi 'denied\|authentication\|must be\|incorrect' && echo 'refused (ok)' || echo 'CHECK MANUALLY')"
caps="$(grep CapEff /proc/self/status | awk '{print $2}')"
printf 'capabilities    %s\n' "$([ "$caps" = "0000000000000000" ] && echo 'all dropped (ok)' || echo "HELD: $caps")"
printf 'setuid elevate  %s\n' "$(grep -q 'NoNewPrivs:\s*1' /proc/self/status && echo 'no_new_privs set (ok)' || echo 'NOT SET')"
echo
echo "=== immutability (agent cannot rewrite its own guards) ==="
printf 'root fs         %s\n' "$(touch /usr/local/bin/probe 2>/dev/null && { rm -f /usr/local/bin/probe; echo 'WRITABLE - GUARDS EDITABLE'; } || echo 'read-only (ok)')"
printf 'pre-commit hook %s\n' "$(touch /opt/autopilot-hooks/probe 2>/dev/null && { rm -f /opt/autopilot-hooks/probe; echo 'WRITABLE - GUARD EDITABLE'; } || echo 'read-only (ok)')"
printf 'system gitconfig %s\n' "$(touch /etc/gitconfig 2>/dev/null && echo 'WRITABLE - GUARD EDITABLE' || echo 'read-only (ok)')"
echo
echo "=== egress (only the allowlist, only through the proxy) ==="
# A refused CONNECT surfaces as curl exit 56 with "response 403" on stderr and
# an http_code of 000, so match the proxy's refusal rather than a status code.
refused() { printf '%s' "$1" | grep -qE '403|407|tunnel failed|Received HTTP code 40'; }
probe_direct="$(curl -sS --max-time 8 --noproxy '*' https://example.com -o /dev/null -w '%{http_code}' 2>&1 || true)"
printf 'direct internet %s\n' "$(printf '%s' "$probe_direct" | grep -qE '^200$' && echo 'REACHABLE - ISOLATION BROKEN' || echo 'no route (ok)')"
allowed="$(curl -sS --max-time 20 https://registry.npmjs.org/ -o /dev/null -w '%{http_code}' 2>&1 || true)"
printf 'allowlisted     %s\n' "$(printf '%s' "$allowed" | grep -qE '^(200|301|302|304)$' && echo 'registry.npmjs.org reachable via proxy (ok)' || echo "BLOCKED ($allowed) - agent cannot install packages")"
denied="$(curl -sS --max-time 20 https://example.com -o /dev/null -w '%{http_code}' 2>&1 || true)"
printf 'not allowlisted %s\n' "$(refused "$denied" && echo 'example.com refused by proxy (ok)' || echo "example.com NOT REFUSED: $denied - ALLOWLIST NOT ENFORCED")"
exfil="$(curl -sS --max-time 20 https://api.openai.com/v1/models -o /dev/null -w '%{http_code}' 2>&1 || true)"
printf 'paid api        %s\n' "$(refused "$exfil" && echo 'api.openai.com refused by proxy (ok, brief 9)' || echo "api.openai.com NOT REFUSED: $exfil")"
exfil2="$(curl -sS --max-time 20 https://pastebin.com -o /dev/null -w '%{http_code}' 2>&1 || true)"
printf 'exfil target    %s\n' "$(refused "$exfil2" && echo 'pastebin.com refused by proxy (ok)' || echo "pastebin.com NOT REFUSED: $exfil2")"
echo
echo "=== containment (all of these must be denied) ==="
printf 'docker socket   %s\n' "$([ -S /var/run/docker.sock ] && echo 'REACHABLE - ISOLATION BROKEN' || echo 'absent (ok)')"
printf 'ssh binary      %s\n' "$(command -v ssh >/dev/null 2>&1 && echo 'PRESENT' || echo 'absent (ok)')"
printf 'ssh keys        %s\n' "$([ -e /root/.ssh ] || [ -e /home/node/.ssh ] && echo 'PRESENT - ISOLATION BROKEN' || echo 'absent (ok)')"
printf 'host home       %s\n' "$([ -e /Users ] && echo 'MOUNTED - ISOLATION BROKEN' || echo 'absent (ok)')"
push_out="$(cd /work/repo && git push --dry-run origin HEAD 2>&1 || true)"
if printf '%s' "$push_out" | grep -qiE 'cannot run ssh|unable to fork|permission denied|could not read|publickey|host key'; then
  printf 'git push        %s\n' "blocked: $(printf '%s' "$push_out" | head -1) (ok)"
else
  printf 'git push        %s\n' "NOT BLOCKED - ISOLATION BROKEN: $(printf '%s' "$push_out" | head -1)"
fi
echo
echo "=== commit-to-main guard (defence in depth, not a seal) ==="
cd /work/repo
if git commit --allow-empty -m 'sandbox guard probe' >/dev/null 2>&1; then
  echo "guard           FAILED - an empty commit landed on $(git rev-parse --abbrev-ref HEAD)"
  git reset --hard HEAD~1 >/dev/null 2>&1
else
  echo "guard           refused a commit on $(git rev-parse --abbrev-ref HEAD) (ok)"
fi
echo "bypassable      yes, by --no-verify or -c core.hooksPath= (git has no"
echo "                mandatory hooks). The host-side tripwire in run.sh"
echo "                detects that case after every autopilot run."
PROBE
    ;;

  proxy-log)
    # The egress audit trail: every request the sandbox made, and whether the
    # allowlist permitted it (TCP_DENIED means refused).
    ensure_network; ensure_proxy
    docker exec "$PROXY_NAME" tail -n "${LINES:-50}" /var/log/squid/access.log
    ;;

  shell)
    ensure_image
    docker run -it "${common_args[@]}" "$IMAGE" bash
    ;;

  autopilot)
    ensure_image
    shift || true
    # Host-side tripwire. The in-container pre-commit hook stops an accidental
    # commit to main, but git offers no mandatory hooks: --no-verify, -c
    # core.hooksPath= and a --global override each bypass it. This check runs
    # outside the sandbox, where the agent cannot reach it, so a violation is
    # caught loudly instead of passing unnoticed.
    main_before="$(git rev-parse main 2>/dev/null || echo none)"

    # No -t: the agent's session must stay non-interactive so the terminal guard
    # in scripts/autopilot-accept.sh cannot be satisfied from inside here.
    rc=0
    docker run -i "${common_args[@]}" "$IMAGE" scripts/autopilot.sh "$@" || rc=$?

    main_after="$(git rev-parse main 2>/dev/null || echo none)"
    if [ "$main_before" != "$main_after" ]; then
      echo
      echo "=============================================================="
      echo "MAIN WAS MOVED FROM INSIDE THE SANDBOX."
      echo "  before: ${main_before}"
      echo "  after:  ${main_after}"
      echo
      echo "Only scripts/autopilot-accept.sh may advance main (brief 3.1, 9)."
      echo "Review what happened before continuing:"
      echo "  git log --oneline ${main_before}..${main_after}"
      echo "To undo:  git branch -f main ${main_before}"
      echo "=============================================================="
      exit 1
    fi
    exit $rc
    ;;

  *)
    sed -n '3,20p' "$0" | sed 's/^# \{0,1\}//'
    exit 1
    ;;
esac
