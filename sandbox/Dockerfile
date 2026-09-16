# Autopilot sandbox image.
#
# This is NOT the application image (see the repo-root Dockerfile for that).
# It is the confinement boundary for running Claude Code with
# --dangerously-skip-permissions, per the note in scripts/autopilot.sh:6.
#
# It carries everything the quality gate in docs/autopilot-brief.md 3.4 needs,
# except Docker itself -- see sandbox/README.md for why, and what covers it.

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
    PYTHONUNBUFFERED=1 \
    npm_config_update_notifier=false

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
        sudo \
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

# The node image already has a uid 1000 'node' user; reuse or re-map it.
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
    mkdir -p /work/repo /work/opptrail-autopilot-logs /home/node/.claude /work/venv; \
    chown -R node:"${GID}" /work /home/node

# Passwordless apt only. Phase F (brief 4.7) must install Playwright's system
# libraries, which needs root; everything else runs unprivileged.
RUN printf '%s\n' \
    'node ALL=(root) NOPASSWD: /usr/bin/apt-get, /usr/bin/apt, /usr/local/bin/npx' \
    > /etc/sudoers.d/autopilot \
    && chmod 0440 /etc/sudoers.d/autopilot

# Structural guard: refuse commits on main from inside the sandbox. The brief
# forbids them (3.1, 9); this makes ignoring that instruction fail rather than
# succeed silently. Owned by root and outside the repo, so the agent cannot edit
# it without deliberately escalating. Limits are documented in README.md.
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

USER node
WORKDIR /work/repo

# Container-global git config only. The repo's .git/config is inside the bind
# mount and shared with the host, so it is never modified from here.
RUN git config --global user.name "OppTrail Autopilot" \
    && git config --global user.email "autopilot@localhost" \
    && git config --global core.hooksPath /opt/autopilot-hooks \
    && git config --global --add safe.directory /work/repo \
    && git config --global advice.detachedHead false

CMD ["bash"]
