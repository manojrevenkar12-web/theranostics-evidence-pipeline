FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src ./src
COPY config ./config
RUN pip install --no-cache-dir . && useradd --uid 10001 tep
ENV TEP_ROOT=/app
USER 10001
ENTRYPOINT ["tep"]
