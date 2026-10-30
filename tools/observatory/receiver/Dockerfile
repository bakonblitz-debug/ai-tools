FROM node:22-bookworm-slim
WORKDIR /app
# better-sqlite3 has no prebuilt binary for every node/arch pair, so it may compile
RUN apt-get update && apt-get install -y --no-install-recommends python3 make g++ && rm -rf /var/lib/apt/lists/*
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY ingest.ts store.ts server.ts ./
ENV DB_PATH=/data/db/otel.db
EXPOSE 4318
CMD ["node", "--experimental-strip-types", "server.ts"]
