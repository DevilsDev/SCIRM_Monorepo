# Production image: build the static bundle, then serve it from unprivileged nginx.
# Vite inlines VITE_* variables at build time, so the API URLs are build args.
#   docker build -t scirm/frontend --build-arg VITE_API_URL=https://api.example.com apps/frontend
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG VITE_API_URL=http://localhost:8000
ARG VITE_WS_URL=ws://localhost:8000/ws
ENV VITE_API_URL=${VITE_API_URL} VITE_WS_URL=${VITE_WS_URL}
RUN npm run build

FROM nginxinc/nginx-unprivileged:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
