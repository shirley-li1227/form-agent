# React 前端镜像：构建静态产物后交给 nginx 托管，并反代 /api 到网关
FROM node:20-alpine AS builder

WORKDIR /app

# 留空表示同源请求（由 nginx 把 /api 反代到网关），部署时一般不需要改
ARG VITE_API_BASE_URL=""
ENV VITE_API_BASE_URL=$VITE_API_BASE_URL

COPY package.json package-lock.json ./
RUN npm ci

COPY tsconfig.json vite.config.ts index.html ./
COPY src ./src
RUN npm run build

FROM nginx:1.27-alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80
