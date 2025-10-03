FROM nginx:1.27-alpine

RUN apk add --no-cache nginx-mod-http-brotli openssl && \
    mkdir -p /etc/nginx/certs

COPY docker-entrypoint.d/10-generate-cert.sh /tmp/10-generate-cert.sh
RUN install -m 0755 /tmp/10-generate-cert.sh /docker-entrypoint.d/10-generate-cert.sh && \
    rm /tmp/10-generate-cert.sh
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
