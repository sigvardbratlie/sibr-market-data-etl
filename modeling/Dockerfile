# Bygges for linux/arm64 (Raspberry Pi / Talos) og evt. amd64. Se Makefile og .github/workflows/images.yml
FROM python:3.11-slim
LABEL org.opencontainers.image.source="https://github.com/sigvardbratlie/sibr-market-data-etl" \
      org.opencontainers.image.authors="sigvardbratlie"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH="/app/src"

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .
# Ikke-root bruker med fast UID, så podene oppfyller Pod Security "restricted"
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin app && chown -R 10001:10001 /app
USER 10001

ENTRYPOINT ["python", "-m", "modeling.main"]
CMD []
