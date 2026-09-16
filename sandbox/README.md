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
```

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

Three further properties, each verified by `run.sh verify`:

- **Runs unprivileged** as `node`, remapped to your UID/GID so files written into
  the bind mount stay yours.
- **Commits are attributed to `OppTrail Autopilot <autopilot@localhost>`** via
  `GIT_AUTHOR_*` / `GIT_COMMITTER_*`. The bind-mounted `.git/config` carries your
  identity and outranks the image's `--global` config, so without the env vars
  every autopilot commit would look like yours. `.git/config` is never modified.
- **Commits to `main` are refused** by a root-owned `pre-commit` hook at
  `/opt/autopilot-hooks`, outside the repo. `main` moves only when you run
  `scripts/autopilot-accept.sh` on the host.

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
agent cannot run it from here. Mounting the Docker socket would hand the
container root on the host and defeat the point. This is unresolved by design and
needs a decision: the brief already requires only `make check-fast` for milestone
commits and reserves full `make check` for `AWAITING_REVIEW`, so the natural split
is for the agent to run everything it can and for the Docker build, smoke test
and `npm audit` to run on the host at review time — which is also when you are
reading the review packet anyway.

**Network egress is open.** The agent needs it for the Claude API and package
installs, so it is not filtered. Brief §9 forbids calling OpenAI and §6.5
requires tests to mock it, but nothing structural stops an outbound call.
Closing this would need an egress proxy with an allowlist.

**`sudo` is limited to `apt-get`/`apt`/`npx`**, because Phase F (§4.7) must
install Playwright's system libraries. An agent could therefore install
arbitrary packages. That does not widen the boundary — there are still no
credentials, no Docker socket, and nothing but the repo mounted — but it is not a
sealed container either.

**The `main` guard raises the bar rather than sealing it.** `git commit
--no-verify` bypasses hooks, and `sudo` could overwrite the hook. Both are
forbidden by brief §9. The guard turns a silent slip into a deliberate act.

The honest summary: this is solid containment against an agent that makes
mistakes, and partial containment against one that actively tries to escape.
