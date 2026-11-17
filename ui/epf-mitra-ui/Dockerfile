# EPF Mitra UI: build Angular, serve the static files with nginx
FROM node:24-alpine AS build
WORKDIR /src
COPY package*.json ./
RUN npm ci
COPY . .
RUN npx ng build --configuration production

FROM nginx:1.27-alpine
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /src/dist/epf-mitra-ui/browser /usr/share/nginx/html
EXPOSE 80
