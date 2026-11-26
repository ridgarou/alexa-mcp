# syntax=docker/dockerfile:1
# For releases supply reviewed digest-pinned bases as build arguments.
ARG NODE_BASE=node:22-trixie-slim
ARG RUNTIME_BASE=debian:trixie-slim

FROM ${NODE_BASE} AS builder
WORKDIR /app
RUN apt-get update \
    && apt-get install -y --no-install-recommends patch \
    && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
# Refuse to build an unmigrated manifest.
RUN node -e 'const p=require("./package.json"); if(p.dependencies.zod!=="4.6.7"||p.dependencies["@modelcontextprotocol/sdk"]!=="1.32.2"||p.dependencies["alexa-remote2"]!=="8.1.1") process.exit(1)' \
    && npm ci --ignore-scripts
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
