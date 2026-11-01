ARG NODE_IMAGE=node:24.13.1-alpine
ARG NGINX_IMAGE=nginx:1.28.0-alpine
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY services/ui ./services/ui
COPY third_party ./third_party
RUN npm run build
FROM ${NGINX_IMAGE}
COPY --from=builder /app/dist/ui /usr/share/nginx/html
COPY services/ui/nginx.conf.template /etc/nginx/templates/default.conf.template
