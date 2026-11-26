# syntax=docker/dockerfile:1
# For releases supply reviewed digest-pinned bases as build arguments.
ARG NODE_BASE=node:22-trixie-slim@sha256:f0960f8dc047f358e3fb428f36ccba21732194fa5f0cac849f401e63e62fb9e6
ARG RUNTIME_BASE=debian:trixie-slim@sha256:8aa5a7bf5a1955bddbe7d74fcdd0b91ab30e74362a8b73af672b0481b35b44a0

FROM ${NODE_BASE} AS builder
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends patch \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci --ignore-scripts
COPY tsconfig.json ./
COPY src ./src
RUN npm run build

FROM builder AS production-dependencies
RUN npm prune --omit=dev --ignore-scripts
COPY patches/alexa-cookie-proxy.patch /tmp/alexa-cookie-proxy.patch
RUN cd /app/node_modules/alexa-cookie2 \
    && node -e 'if(require("./package.json").version!=="5.0.6") process.exit(1)' \
    && patch --dry-run --batch --forward --fuzz=0 -p1 < /tmp/alexa-cookie-proxy.patch \
    && patch --batch --forward --fuzz=0 -p1 < /tmp/alexa-cookie-proxy.patch \
    && node --check lib/proxy.js

FROM ${RUNTIME_BASE} AS runtime
ENV NODE_ENV=production HOME=/home/node
RUN apt-get update \
    && apt-get upgrade -y --no-install-recommends \
    && apt-get install -y --no-install-recommends ca-certificates libatomic1 libstdc++6 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 1000 node \
    && useradd --uid 1000 --gid 1000 --create-home --shell /usr/sbin/nologin node
COPY --from=builder /usr/local/bin/node /usr/local/bin/node
WORKDIR /app
COPY --chown=0:0 package.json package-lock.json ./
COPY --chown=0:0 --from=production-dependencies /app/node_modules ./node_modules
COPY --chown=0:0 --from=builder /app/dist ./dist
RUN chmod -R go-w /app \
    && install -d -m 0700 -o node -g node /app/.auth \
    && node --version \
    && node --check dist/index.js \
    && node --check dist/alexa.js \
    && node --check dist/auth-cli.js
USER node
CMD ["node", "dist/index.js"]
