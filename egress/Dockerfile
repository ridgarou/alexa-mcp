# syntax=docker/dockerfile:1
FROM debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0
RUN apt-get update \
 && apt-get upgrade -y --no-install-recommends \
 && apt-get install -y --no-install-recommends squid ca-certificates \
 && rm -rf /var/lib/apt/lists/* \
 && id proxy \
 && /usr/sbin/squid -v
USER proxy
ENTRYPOINT ["/usr/sbin/squid", "-N", "-f", "/etc/alexa-egress/squid.conf"]
