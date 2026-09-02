# Vibration Platform Frontend — Node.js Docker image
#
# Dev server (hot reload, for local testing):
#   docker build --target dev -t vibration-frontend:dev .
#   docker run --rm -p 5173:5173 -v "%cd%:/app" -v /app/node_modules vibration-frontend:dev
#
# Production preview (built static assets):
#   docker build --target preview -t vibration-frontend:preview .
#   docker run --rm -p 4173:4173 vibration-frontend:preview

FROM node:20-alpine AS base

WORKDIR /app

COPY package.json package-lock.json ./
RUN npm ci

COPY . .

# ---------------------------------------------------------------------------
# Dev — Vite dev server (default target for testing)
# ---------------------------------------------------------------------------
FROM base AS dev

EXPOSE 5173

# --host 0.0.0.0 makes the server reachable from outside the container
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0", "--port", "5173"]

# ---------------------------------------------------------------------------
# Build — compile TypeScript and produce static assets
# ---------------------------------------------------------------------------
FROM base AS build

ARG VITE_API_BASE_URL=http://host.docker.internal:8000
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

RUN npm run build

# ---------------------------------------------------------------------------
# Preview — serve the production build with nginx
# ---------------------------------------------------------------------------
FROM nginx:alpine AS preview

COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 4173 4443

CMD ["nginx", "-g", "daemon off;"]
