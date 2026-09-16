# Egress proxy for the autopilot sandbox.
#
# The sandbox sits on an internal Docker network with no route off the host.
# Everything it reaches, it reaches through here, and only if the hostname is in
# allowlist.conf. Domains are matched on the CONNECT request, so HTTPS is
# filtered without terminating or inspecting TLS.
FROM debian:bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends squid ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# squid drops to the unprivileged 'proxy' user, which cannot open /dev/stdout or
# /dev/stderr by path: squid resolves the symlink and then requires the parent
# directory (/dev) to be writable by that user. So the access log is a real file
# in a directory proxy owns. Startup and error output still reaches
# `docker logs` because -d 1 writes to the inherited stderr fd directly.
# Read the access log with: sandbox/run.sh proxy-log
RUN mkdir -p /var/log/squid && chown -R proxy:proxy /var/log/squid

COPY squid.conf /etc/squid/squid.conf
COPY allowlist.conf /etc/squid/allowlist.conf

EXPOSE 3128
# -N runs in the foreground; -d 1 sends the access log to stderr so
# `docker logs opptrail-autopilot-proxy` shows exactly what was requested and
# whether it was allowed. That log is the audit trail for egress.
CMD ["squid", "-N", "-d", "1", "-f", "/etc/squid/squid.conf"]
