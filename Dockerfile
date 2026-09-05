FROM ubuntu:24.04

ENV DEBIAN_FRONTEND=noninteractive
RUN apt-get update \
    && apt-get install -y --no-install-recommends python3 python3-venv ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY tests ./tests
RUN python3 -m venv /opt/tecolote \
    && /opt/tecolote/bin/pip install --no-cache-dir '.[dev]' \
    && /opt/tecolote/bin/pytest

ENV PATH="/opt/tecolote/bin:${PATH}"
ENTRYPOINT ["tecolote"]
CMD ["--version"]
