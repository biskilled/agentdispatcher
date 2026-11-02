ARG NODE_IMAGE
ARG NGINX_IMAGE
FROM ${NODE_IMAGE} AS builder
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY services/ui ./services/ui
COPY third_party ./third_party
RUN npm run build
FROM ${NGINX_IMAGE}
RUN apk upgrade --no-cache
COPY --from=builder /app/dist/ui /usr/share/nginx/html
COPY services/ui/nginx.conf.template /etc/nginx/templates/default.conf.template
