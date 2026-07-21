FROM node:20-slim

WORKDIR /app

RUN corepack enable

COPY package.json ./
RUN pnpm install

COPY . .

EXPOSE 3000
CMD ["pnpm", "dev"]
