# syntax=docker/dockerfile:1.7
# pg_dump/pg_restore plus age for encrypted backups. Runs only on demand (Compose profile "ops").
# Optional build secret `build_ca` as in backend/Dockerfile.
FROM postgres:16-alpine
RUN --mount=type=secret,id=build_ca,required=false \
    if [ -f /run/secrets/build_ca ]; then cp /etc/ssl/certs/ca-certificates.crt /tmp/ca.bak \
      && cat /run/secrets/build_ca >> /etc/ssl/certs/ca-certificates.crt; fi; \
    apk add --no-cache age; \
    if [ -f /tmp/ca.bak ]; then mv /tmp/ca.bak /etc/ssl/certs/ca-certificates.crt; fi
COPY backup.sh restore.sh /usr/local/bin/
ENTRYPOINT []
CMD ["backup.sh"]
