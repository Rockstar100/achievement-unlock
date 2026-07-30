# Open-source Flipkart scraper API (dvishal485/flipkart-scraper-api)
# https://github.com/dvishal485/flipkart-scraper-api

FROM rust:1.85-slim-bookworm AS builder
RUN apt-get update \
    && apt-get install -y --no-install-recommends git pkg-config libssl-dev ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /src
RUN git clone --depth 1 https://github.com/dvishal485/flipkart-scraper-api.git .
# Bind address used at compile-time defaults; override at runtime with DEPLOYMENT_URL
ENV DEPLOYMENT_URL=0.0.0.0:3000
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*
COPY --from=builder /src/target/release/flipkart-scraper-api /usr/local/bin/
# Host:port only (no scheme) — binds inside the container
ENV DEPLOYMENT_URL=0.0.0.0:3000
EXPOSE 3000
CMD ["flipkart-scraper-api"]
