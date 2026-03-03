# PipelineHealer Frontend Dockerfile
FROM docker.io/oven/bun:1 as builder

WORKDIR /app

# Copy package files (supports Bun v1 text lockfile and legacy binary lockfile).
COPY package.json bun.lock* ./

# Install dependencies
RUN bun install --frozen-lockfile

# Copy source files
COPY . .

# Build the application
RUN bun run build

# Production stage
FROM docker.io/library/nginx:alpine

RUN apk add --no-cache gettext

# Copy built assets
COPY --from=builder /app/dist /usr/share/nginx/html

# Copy templated nginx config and startup entrypoint
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 3000

ENTRYPOINT ["/entrypoint.sh"]
