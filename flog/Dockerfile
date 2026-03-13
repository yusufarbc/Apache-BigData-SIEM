FROM alpine:3.20

ARG FLOG_VERSION=0.4.3

RUN apk add --no-cache bash curl kcat ca-certificates tzdata && \
    ARCH="$(uname -m)"; \
    if [ "$ARCH" = "x86_64" ]; then ARCH="amd64"; \
    elif [ "$ARCH" = "aarch64" ]; then ARCH="arm64"; \
    else echo "Unsupported architecture: $ARCH" && exit 1; fi; \
    curl -fsSL "https://github.com/mingrammer/flog/releases/download/v${FLOG_VERSION}/flog_${FLOG_VERSION}_linux_${ARCH}.tar.gz" \
    | tar -xz -C /usr/local/bin flog && \
    chmod +x /usr/local/bin/flog

COPY publish_flog.sh /usr/local/bin/publish_flog.sh
RUN sed -i 's/\r$//' /usr/local/bin/publish_flog.sh && chmod +x /usr/local/bin/publish_flog.sh

ENTRYPOINT ["/usr/local/bin/publish_flog.sh"]
