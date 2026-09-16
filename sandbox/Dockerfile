# Autopilot sandbox image.
#
# This is NOT the application image (see the repo-root Dockerfile for that).
# It is the confinement boundary for running Claude Code with
# --dangerously-skip-permissions, per the note in scripts/autopilot.sh:6.
#
# It carries everything the quality gate in docs/autopilot-brief.md 3.4 needs,
# except Docker itself -- see sandbox/README.md and scripts/autopilot-gate.sh.

FROM node:22-bookworm-slim

# Pinned so an unattended 40-session run cannot change agent behaviour midway.
# Override with: --build-arg CLAUDE_CODE_VERSION=x.y.z
ARG CLAUDE_CODE_VERSION=2.1.233

# Host UID/GID so files written into the bind-mounted repo stay owned by you
# on Linux hosts. Docker Desktop on macOS maps ownership already.
ARG UID=1000
ARG GID=1000

ENV DEBIAN_FRONTEND=noninteractive \
    UV_PYTHON_INSTALL_DIR=/opt/uv-python \
    # Keep the container's virtualenv out of the bind-mounted repo. The host's
    # backend/.venv is macOS aarch64 / Python 3.14; a container `uv sync` would
    # overwrite it with Linux binaries and break `uv run pytest` on the host.
    UV_PROJECT_ENVIRONMENT=/work/venv \
    PLAYWRIGHT_BROWSERS_PATH=/work/pw-browsers \
    # The root filesystem is mounted read-only at runtime, so the CLI must not
    # try to rewrite its own installation.
    DISABLE_AUTOUPDATER=1 \
    PYTHONUNBUFFERED=1 \
    npm_config_update_notifier=false

# No sudo, and no other route to root: see sandbox/README.md.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        curl \
        git \
        jq \
        less \
        make \
        procps \
        ripgrep \
        build-essential \
        libffi-dev \
        # WeasyPrint runtime libraries, matching the application image. These are
        # what make the PDF export test actually run here instead of skipping as
        # it does on a macOS host (see CLAUDE.md, WeasyPrint section).
        libharfbuzz-subset0 \
        libpango-1.0-0 \
        libpangoft2-1.0-0 \
    && rm -rf /var/lib/apt/lists/*

# uv, taken from the same image the application build uses.
COPY --from=ghcr.io/astral-sh/uv:python3.13-bookworm-slim /usr/local/bin/uv /usr/local/bin/uvx /usr/local/bin/

# Python 3.13 (backend requires >=3.13; Debian bookworm ships 3.11), installed to
# a shared location so the unprivileged agent user can use it.
RUN uv python install 3.13 \
    && chmod -R a+rX /opt/uv-python \
    && ln -sf "$(uv python find 3.13)" /usr/local/bin/python3 \
    && ln -sf /usr/local/bin/python3 /usr/local/bin/python

RUN npm install -g "@anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}"

# Playwright's system libraries, installed now as root so the agent never needs
# root later. Browser binaries are NOT baked in: they are version-specific, and
# Phase F pins the Playwright version in package.json. The agent installs them
# unprivileged into PLAYWRIGHT_BROWSERS_PATH, which run.sh backs with a volume.
RUN npx --yes playwright@latest install-deps chromium \
    && rm -rf /var/lib/apt/lists/* /root/.npm

# Tolerates IDs that already exist in the base image -- a macOS host's staff
# group is gid 20, which Debian already uses for dialout.
RUN set -eu; \
    if [ "${GID}" != "$(id -g node)" ]; then \
        getent group "${GID}" >/dev/null || groupmod -g "${GID}" node; \
        usermod -g "${GID}" node; \
    fi; \
    if [ "${UID}" != "$(id -u node)" ] && ! getent passwd "${UID}" >/dev/null; then \
        usermod -u "${UID}" node; \
    fi; \
    mkdir -p /work/repo /work/opptrail-autopilot-logs /home/node/.claude \
        /work/venv /work/pw-browsers; \
    chown -R node:"${GID}" /work /home/node

# Structural guard: refuse commits on main from inside the sandbox. The brief
# forbids them (3.1, 9); this makes an accidental commit fail rather than
# succeed silently. Root-owned and outside the repo, on a read-only root
# filesystem. It is defence in depth, not a seal -- git has no mandatory hooks,
# so --no-verify and -c core.hooksPath= bypass it. The host-side tripwire in
# sandbox/run.sh catches that case. See sandbox/README.md.
RUN mkdir -p /opt/autopilot-hooks \
    && printf '%s\n' \
        '#!/bin/sh' \
        '# Autopilot sandbox: main is advanced only by scripts/autopilot-accept.sh on the host.' \
        'branch="$(git rev-parse --abbrev-ref HEAD 2>/dev/null || echo unknown)"' \
        'case "$branch" in' \
        '  main|master)' \
        '    echo "sandbox: refusing to commit to $branch." >&2' \
        '    echo "Autopilot commits only to autopilot/phase-<ID> branches (brief 3.1)." >&2' \
        '    exit 1 ;;' \
        'esac' \
        'exit 0' \
        > /opt/autopilot-hooks/pre-commit \
    && chmod 0555 /opt/autopilot-hooks/pre-commit \
    && chmod 0555 /opt/autopilot-hooks

# System-level git config, written as root onto the read-only root filesystem.
# This deliberately is NOT ~/.gitconfig: the agent's home is a writable volume,
# so a --global setting could simply be edited. The repo's own .git/config lives
# in the bind mount and is never touched from here.
RUN git config --system core.hooksPath /opt/autopilot-hooks \
    && git config --system --add safe.directory /work/repo \
    && git config --system advice.detachedHead false \
    && git config --system user.name "OppTrail Autopilot" \
    && git config --system user.email "autopilot@localhost" \
    && chmod 0444 /etc/gitconfig

USER node
WORKDIR /work/repo

CMD ["bash"]
