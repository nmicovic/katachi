# Container image running the katachi CLI:
#   docker build -t katachi .
#   docker run --rm -v "$PWD:/data" katachi validate /data/katachi.yaml /data
FROM python:3.13-slim

COPY --from=ghcr.io/astral-sh/uv:0.8 /uv /bin/uv

WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_NO_DEV=1

# Install dependencies first (cached layer), then the project
COPY uv.lock pyproject.toml README.md /app/
RUN uv sync --frozen --no-install-project --extra azure
COPY src /app/src
RUN uv sync --frozen --extra azure

RUN useradd --create-home katachi
USER katachi
ENV PATH="/app/.venv/bin:$PATH"
WORKDIR /data
ENTRYPOINT ["katachi"]
CMD ["--help"]
