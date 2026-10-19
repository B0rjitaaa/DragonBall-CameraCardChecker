# --- Build estático ---
FROM node:20-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN if [ -f package-lock.json ]; then npm ci; else npm install; fi
COPY . .
RUN npm run build

# --- Nginx: sirve la SPA, /media y hace proxy de /api y /admin a Gunicorn ---
FROM nginx:1.27-alpine
COPY nginx/app.conf /etc/nginx/snippets/app.conf
COPY nginx/default.conf /etc/nginx/conf.d/default.conf
COPY nginx/https.conf /etc/nginx/https.conf.available
COPY --chmod=755 nginx/40-https.sh /docker-entrypoint.d/40-https.sh
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80 443
