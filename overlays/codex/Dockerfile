ARG NODE_BASE_IMAGE
ARG BASE_RUNTIME
FROM ${NODE_BASE_IMAGE} AS prepare
WORKDIR /source
RUN curl --fail --location --silent --show-error https://codeload.github.com/openclaw/openclaw/tar.gz/6f91eda9c72d6b4c2640cb76b5a753e64089f6f2 -o /tmp/source.tar.gz \
 && echo '8e0f0332bbdb798834148895d57c19e6b622dbb3b5eac39801c14c316ad93d0c  /tmp/source.tar.gz' | sha256sum --check --strict \
 && tar -xzf /tmp/source.tar.gz --strip-components=1 \
 && rm /tmp/source.tar.gz \
 && corepack pnpm --filter @openclaw/codex add --lockfile-only --ignore-scripts --save-exact @openai/codex@0.160.1
WORKDIR /install
COPY overlays/codex/package.json overlays/codex/package-lock.json ./
RUN npm ci --ignore-scripts --omit=dev --registry=https://registry.npmjs.org \
 && node node_modules/@openai/codex/bin/codex.js --version

FROM ${BASE_RUNTIME}
USER root
ENV OPENAI_CODEX_VERSION=0.160.1
LABEL org.raw-labs.runtime.codex-version="0.160.1"
COPY --from=prepare /install/node_modules/ /app/node_modules/openclaw/.oce-codex-0.160.1/node_modules/
COPY --from=prepare /source/pnpm-lock.yaml /app/node_modules/openclaw/pnpm-lock.yaml
COPY --from=prepare /source/extensions/codex/package.json /app/node_modules/openclaw/extensions/codex/package.json
COPY --from=prepare /source/extensions/codex/package.json /app/node_modules/openclaw/dist/extensions/codex/package.json
COPY overlays/codex/relink.mjs /tmp/relink-runtime-codex.mjs
COPY upstream/build-runtime-assets.mjs /tmp/runtime-inventory-pinned.mjs
RUN node /tmp/relink-runtime-codex.mjs \
 && node /tmp/runtime-inventory-pinned.mjs inventory /app/node_modules/openclaw /opt/oce/runtime \
 && node -e 'const fs=require("fs"),crypto=require("crypto"),p="/opt/oce/runtime/provenance.json",v=JSON.parse(fs.readFileSync(p));v.lockfileSha256=crypto.createHash("sha256").update(fs.readFileSync("/app/node_modules/openclaw/pnpm-lock.yaml")).digest("hex");v.runtimeOverlay={codexVersion:"0.160.1"};fs.writeFileSync(p,JSON.stringify(v,null,2)+"\n");' \
 && test "$(codex --version)" = "codex-cli 0.160.1" \
 && codex debug models --bundled > /tmp/catalog.json \
 && node -e 'const p=require("/tmp/catalog.json");if(!p.models.some(m=>m.slug==="gpt-6.1-sol"))throw new Error("GPT-6.1 metadata absent");' \
 && rm /tmp/relink-runtime-codex.mjs /tmp/runtime-inventory-pinned.mjs /tmp/catalog.json
USER node
