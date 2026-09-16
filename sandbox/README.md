# Autopilot sandbox

`scripts/autopilot.sh` runs Claude Code with `--dangerously-skip-permissions`,
which removes every approval prompt. Its own header says to run it "INSIDE a
container/VM that mounts only this repo". This directory is that container.

This is not the application image. The repo-root `Dockerfile` builds OppTrail
itself; this one builds an environment to *work on* OppTrail in.

## Quick start

```bash
sandbox/run.sh build       # build the image (a few minutes, once)
sandbox/run.sh login       # one-time Claude Code sign-in inside the sandbox
sandbox/run.sh verify      # print what the sandbox can and cannot reach
MAX_RUNS=1 sandbox/run.sh autopilot   # one supervised run
sandbox/run.sh autopilot   # unattended, up to MAX_RUNS milestones
sandbox/run.sh proxy-log   # what egress was requested, and what was refused
```

`MODEL` picks the model for the agent session (`opus`, `sonnet`, `haiku`, or a
full model id); unset uses the CLI default, which is what the first three
milestones ran on. Worth setting for the two milestones that are hardest to
recover from — the Alembic baseline (F.4) and the frontend decomposition
(Phase 2):

```bash
MODEL=opus MAX_RUNS=1 sandbox/run.sh autopilot
```

The chosen model is printed in each run header and therefore recorded in the
run logs under `../opptrail-autopilot-logs/`.

`sandbox/run.sh shell` gives an interactive shell in the same environment, which
is the fastest way to reproduce something the agent hit.

## Sign-in

Host Claude Code credentials live in the macOS Keychain, so a Linux container
cannot inherit them. The sandbox keeps its **own** Claude home in the Docker
volume `opptrail-autopilot-claude`; `sandbox/run.sh login` populates it once and
later runs reuse it. Your `~/.claude` is never mounted, so the agent cannot read
your other projects' sessions or history.

Alternatively, export `ANTHROPIC_API_KEY` and `run.sh` passes it through. Note
that this bills the API rather than a subscription.

## What the boundary actually is

Containment comes from what `run.sh` mounts, not from instructions in the brief.

| Mounted | Path in sandbox | Why |
|---|---|---|
| This repo | `/work/repo` (rw) | the work |
| Log directory | `/work/opptrail-autopilot-logs` (rw) | `autopilot.sh` writes run logs outside the repo |
| Agent Claude home | `/home/node/.claude` (volume) | sign-in persistence, separate from yours |

| Deliberately absent | Consequence |
|---|---|
| `~/.ssh` and any git credential | `git push` fails: `cannot run ssh`. Brief §9's no-push rule enforced by absence, not obedience. The image has no `ssh` binary at all |
| `/var/run/docker.sock` | socket access is root-equivalent on the host and would make this sandbox decorative |
| `~/.claude` | your other projects stay invisible |
| `$HOME`, `/tmp`, every other host path | the repo is the whole blast radius |
| `sudo`, and any setuid path to root | the image ships no `sudo`; `--cap-drop ALL` plus `no-new-privileges` means a setuid binary cannot elevate either |
| a route to the internet | the sandbox sits alone on an `--internal` Docker network whose only other member is the egress proxy |

Further properties, each verified by `run.sh verify`:

- **Runs unprivileged** as `node`, remapped to your UID/GID so files written into
  the bind mount stay yours, with all capabilities dropped.
- **Read-only root filesystem.** Only `/work/repo`, the log directory, the agent's
  home, the venv and the browser cache are writable, so the agent cannot rewrite
  its own toolchain, the commit hook, or `/etc/gitconfig`.
- **Egress is allowlisted.** Everything the sandbox reaches goes through
  `sandbox/proxy`, which permits only the hostnames in `proxy/allowlist.conf` and
  logs every request, allowed or refused. `api.openai.com` and general hosts such
  as `pastebin.com` are refused, which is brief §9 enforced by routing rather than
  by instruction. Read the trail with `sandbox/run.sh proxy-log`.
- **Commits are attributed to `OppTrail Autopilot <autopilot@localhost>`** via
  `GIT_AUTHOR_*` / `GIT_COMMITTER_*`. The bind-mounted `.git/config` carries your
  identity and outranks the image's `--global` config, so without the env vars
  every autopilot commit would look like yours. `.git/config` is never modified.

### The `main` guard, and why it is not a seal

A root-owned `pre-commit` hook at `/opt/autopilot-hooks` refuses commits on
`main`. It stops the accident. It does **not** stop a determined agent: git has
no mandatory hooks, and `git commit --no-verify`, `git -c core.hooksPath=` and a
`--global` override each bypass it. This was tested rather than assumed; all
three bypasses succeed.

So the real control is on the host. `sandbox/run.sh autopilot` records `main`'s
SHA before launching the container and checks it afterwards. If `main` moved, it
prints what happened, how to inspect it and how to undo it, then exits non-zero.
That check runs outside the sandbox, where the agent cannot reach it.

Note the distinction: host isolation, credentials and egress are *boundaries*.
The `main` rule is a *workflow* control, and a local commit to `main` is a
visible, recoverable process violation rather than an escape — it cannot reach
the remote and cannot create an acceptance tag.

If you want `main` sealed by construction too, the change is to mount a clone
rather than this repo, with the real repository bind-mounted read-only as its
`origin`, and have `scripts/autopilot-accept.sh` fetch from the clone instead of
merging a local branch. That is a workflow change, so it is not done here.

Container builds are also kept off your host toolchain. `UV_PROJECT_ENVIRONMENT`
points at `/work/venv`, and `frontend/node_modules`, `.next` and `out` are
overlaid with volumes. Without this, a container `uv sync` would replace your
macOS / Python 3.14 `backend/.venv` with Linux binaries, and `npm ci` would
replace native `@swc` and `sharp` builds, breaking `uv run pytest` and
`npm run build` on the host.

Verified in this environment: the backend suite runs **39 passed** in the
sandbox, against 38 passed + 1 skipped on macOS. The extra test is the WeasyPrint
PDF export (see `CLAUDE.md`), so PDF changes are genuinely exercised here.

## Limits, stated plainly

**No Docker inside the sandbox.** The quality gate in
`docs/autopilot-brief.md` §3.4 ends with "Docker build + smoke test", and the
agent cannot run it from here; mounting the Docker socket would hand the
container root on the host. This is settled rather than open: the gate is split.
The agent runs every other item, and you run `scripts/autopilot-gate.sh <ID>` on
the host, which builds the application image from the phase branch and smoke
tests health, sign-up, opportunity creation, PDF export and frontend serving. It
writes a receipt keyed to the branch commit into a directory that is never
mounted here, and `scripts/autopilot-accept.sh` refuses to accept a phase
without one. Brief §3.4 documents this and forbids quietly dropping the deferred
step from `make check`.

**DNS resolution still answers for names outside the allowlist**, because
Docker's embedded resolver replies regardless of routing. Nothing can be fetched
over those names — there is no route, and the proxy refuses them — but a
determined agent could in principle signal small amounts of data through DNS
queries. Closing that means running a filtering resolver beside the proxy.

**Allowlisted hosts are trusted.** `registry.npmjs.org`, `pypi.org` and
`github.com` have to be reachable for the agent to install anything, and they
serve arbitrary user-published content. The allowlist bounds *where* traffic can
go, not what those hosts return. Keep `proxy/allowlist.conf` minimal; every
addition widens this.

**Playwright browsers are not baked in.** The system libraries are, but the
browser binaries are version-specific and Phase F pins the Playwright version in
`package.json`, so the agent installs them unprivileged into
`PLAYWRIGHT_BROWSERS_PATH`. Chromium will need `--no-sandbox` in its launch
options, which is standard in containers — do not add capabilities to work
around it.

The honest summary: host isolation, credentials, privilege and egress are sealed
and tested. The `main` rule is enforced by detection rather than prevention, and
the holes left open on purpose are DNS names and whatever the allowlisted
package registries choose to serve.
