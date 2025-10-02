FROM nginx:1.27-alpine

RUN apk add --no-cache nginx-mod-http-brotli openssl && \
    mkdir -p /etc/nginx/certs

COPY docker-entrypoint.d/ /docker-entrypoint.d/
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

RUN chmod +x /docker-entrypoint.d/*.sh

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
