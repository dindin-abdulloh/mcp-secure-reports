FROM python:3.12-slim

WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir .

ENV DATA_DIR=/data \
    CONFIG_PATH=/app/config/roles.json \
    BACKEND=mock
VOLUME ["/data"]

# MCP over stdio: run with `docker run -i -e VAULT_MASTER_KEY=... -e MCP_ROLE=... image`
ENTRYPOINT ["secure-reports-mcp"]
