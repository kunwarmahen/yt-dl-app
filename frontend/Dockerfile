FROM node:18-alpine AS builder

WORKDIR /app

COPY package.json package-lock.json* yarn.lock* ./

RUN npm install || npm ci

COPY src/ ./src/
COPY public/ ./public/

# Build args for API URL
ARG REACT_APP_API_URL=/api

ENV REACT_APP_API_URL=${REACT_APP_API_URL}

RUN npm run build

FROM docker.io/library/nginx:alpine

COPY --from=builder /app/build /usr/share/nginx/html

RUN rm /etc/nginx/conf.d/default.conf

COPY nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]