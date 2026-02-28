FROM alpine:latest

RUN apk add --no-cache \
    bash \
    curl \
    jq \
    rclone \
    mosquitto-clients \
    tzdata

WORKDIR /app

COPY . /app
RUN chmod +x /app/*.sh

CMD ["/bin/bash", "/app/frigate_watchdog.sh"]