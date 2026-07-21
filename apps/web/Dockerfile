# Monorepo-aware build. Build context is the REPO ROOT (see docker-compose.yml /
# render.yaml) so the pnpm workspace and packages/shared are available and the
# web app's `workspace:*` dependency resolves.
FROM node:20-slim

WORKDIR /app

# Pin pnpm explicitly. Without this, corepack fetches the latest pnpm (11.x),
# which requires Node 22.13+ and fails on this Node 20 base.
RUN corepack enable && corepack prepare pnpm@9.15.0 --activate

# Copy workspace manifests first for dependency-layer caching.
COPY package.json pnpm-workspace.yaml ./
COPY packages/shared/package.json packages/shared/package.json
COPY apps/web/package.json apps/web/package.json
RUN pnpm install

# Copy the rest of the workspace the web app needs.
COPY packages/shared packages/shared
COPY apps/web apps/web

WORKDIR /app/apps/web
EXPOSE 3000
CMD ["pnpm", "dev"]
