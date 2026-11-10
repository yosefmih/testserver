FROM gogost/gost:3.3.3 AS gost

FROM node:24-trixie-slim

RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates chromium fonts-liberation fonts-noto-color-emoji xvfb \
 && rm -rf /var/lib/apt/lists/* \
 && useradd --system --no-create-home --shell /usr/sbin/nologin egress \
 && install -d -m 1777 /tmp/.X11-unix

COPY --from=gost /bin/gost /usr/local/bin/gost
COPY chromium-policy.json /etc/chromium/policies/managed/browser-app.json
COPY entrypoint.sh egress-config.mjs server.mjs /app/

EXPOSE 8080
ENTRYPOINT ["bash", "/app/entrypoint.sh"]
