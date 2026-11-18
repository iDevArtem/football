# Stage 1: Build Frontend SPA
FROM node:26-alpine AS builder

WORKDIR /app

# Build-time argument for API Base URL (bakes into Vite client bundle)
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}

# Install dependencies (devDependencies included because NODE_ENV is not production yet)
COPY package*.json ./
RUN npm ci

# Copy source and build SPA
COPY . .
RUN npm run build

# Stage 2: Serve SPA with Nginx
FROM nginx:1.27-alpine AS runner

WORKDIR /usr/share/nginx/html

ENV NODE_ENV=production

# Remove default static assets
RUN rm -rf ./*

# Copy built artifacts from builder stage
COPY --from=builder /app/dist ./
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:80/healthz || exit 1

CMD ["nginx", "-g", "daemon off;"]
