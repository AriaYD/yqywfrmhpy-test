# CampusPath Web → Cloud Run。`/api/*` 由 next rewrites 反代到
# CAMPUSPATH_API_ORIGIN（部署时注入 campuspath-api 的 Cloud Run URL），
# 浏览器侧仍是同源——不为演示放开 CORS。
FROM oven/bun:1.2-slim

WORKDIR /app
COPY package.json bun.lock ./
RUN bun install --frozen-lockfile
COPY . .
# rewrites 在 build 时烧进 routes-manifest——API 源必须在**构建期**就位，
# Cloud Run 的运行时环境变量对它无效（踩过：代理 500 回落 127.0.0.1）
ENV CAMPUSPATH_API_ORIGIN=https://campuspath-api-786160486093.asia-east2.run.app
RUN bun run build

ENV NODE_ENV=production
CMD ["sh", "-c", "bun run start -- -p ${PORT:-8080}"]
