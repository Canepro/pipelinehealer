# PipelineHealer Frontend Dockerfile
FROM docker.io/oven/bun:1 as builder

WORKDIR /app

# Build-time auth/runtime config injected from compose env.
ARG VITE_AUTH_MODE=none
ARG VITE_ENTRA_TENANT_ID=
ARG VITE_ENTRA_CLIENT_ID=
ARG VITE_ENTRA_AUTHORITY=
ARG VITE_ENTRA_API_SCOPE=
ARG VITE_ENTRA_REDIRECT_URI=
ARG VITE_ENTRA_POST_LOGOUT_REDIRECT_URI=
ARG VITE_API_URL=
ARG VITE_API_AUTH_KEY=
ARG VITE_API_TIMEOUT_MS=15000
ENV VITE_AUTH_MODE=$VITE_AUTH_MODE \
    VITE_ENTRA_TENANT_ID=$VITE_ENTRA_TENANT_ID \
    VITE_ENTRA_CLIENT_ID=$VITE_ENTRA_CLIENT_ID \
    VITE_ENTRA_AUTHORITY=$VITE_ENTRA_AUTHORITY \
    VITE_ENTRA_API_SCOPE=$VITE_ENTRA_API_SCOPE \
    VITE_ENTRA_REDIRECT_URI=$VITE_ENTRA_REDIRECT_URI \
    VITE_ENTRA_POST_LOGOUT_REDIRECT_URI=$VITE_ENTRA_POST_LOGOUT_REDIRECT_URI \
    VITE_API_URL=$VITE_API_URL \
    VITE_API_AUTH_KEY=$VITE_API_AUTH_KEY \
    VITE_API_TIMEOUT_MS=$VITE_API_TIMEOUT_MS

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
