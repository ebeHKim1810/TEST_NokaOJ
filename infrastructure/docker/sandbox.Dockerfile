# Minimal unprivileged sandbox container image for executing untrusted student/generator code
FROM debian:bookworm-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    g++ python3 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /work
USER 65534:65534
