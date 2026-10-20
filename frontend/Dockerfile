# ── Stage 1: Build Vue 3 Frontend ──
FROM node:20-alpine AS builder

WORKDIR /app

ARG VITE_TELEGRAM_BOT_ID=""
ARG VITE_GOOGLE_CLIENT_ID=""
ARG VITE_CHUNK_SIZE_MB=8
ENV VITE_TELEGRAM_BOT_ID=$VITE_TELEGRAM_BOT_ID \
    VITE_GOOGLE_CLIENT_ID=$VITE_GOOGLE_CLIENT_ID \
    VITE_CHUNK_SIZE_MB=$VITE_CHUNK_SIZE_MB

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# ── Stage 2: Serve via Nginx Alpine ──
FROM nginx:alpine AS runner

COPY --from=builder /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
