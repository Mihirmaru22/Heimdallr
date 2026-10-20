# API, worker and beat all use this image; the command differs per service.
FROM python:3.13-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.11.32 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY . .
RUN uv sync --frozen --no-dev \
    && useradd --system --uid 10001 --home /app webdata \
    && mkdir -p /data && chown webdata /data
USER webdata
# The commit this image was built from (no .git inside), shown in the app's version check.
ARG WEBDATA_BUILD_SHA=unknown
ARG WEBDATA_BUILD_BRANCH=
ENV WEBDATA_DATA_DIR=/data WEBDATA_BUILD_SHA=$WEBDATA_BUILD_SHA WEBDATA_BUILD_BRANCH=$WEBDATA_BUILD_BRANCH
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
