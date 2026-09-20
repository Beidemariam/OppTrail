$ErrorActionPreference = "Stop"
$Port = if ($env:PORT) { $env:PORT } else { "8000" }

# The image runs as uid 1000, not root (ADR 0011 item 5). Docker Desktop's
# Windows bind-mount translation (WSL2/Hyper-V) does not enforce POSIX
# ownership the way a native Linux host does, so no chmod-equivalent is
# needed here -- see scripts/start_linux.sh / start_mac.sh for the two
# platforms where it is.
New-Item -ItemType Directory -Force -Path data | Out-Null

docker build -t opptrail .
docker rm -f opptrail 2>$null
docker run `
  --name opptrail `
  --env-file .env `
  -p "${Port}:8000" `
  -v "${PWD}/data:/data" `
  opptrail
