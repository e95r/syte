FROM nginx:1.27-alpine

RUN apk add --no-cache openssl curl && \
    mkdir -p /etc/nginx/certs

COPY docker-entrypoint.d/ /docker-entrypoint.d/
RUN sed -i 's/\r$//' /docker-entrypoint.d/*.sh && \
    chmod +x /docker-entrypoint.d/*.sh
COPY nginx.conf /etc/nginx/nginx.conf
COPY conf.d/ /etc/nginx/conf.d/

EXPOSE 80 443

CMD ["nginx", "-g", "daemon off;"]
