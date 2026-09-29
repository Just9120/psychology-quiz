FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f

ARG APP_REVISION=UNSET
LABEL org.opencontainers.image.revision=$APP_REVISION
ENV APP_REVISION=$APP_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.lock /app/requirements.lock
RUN pip install --no-cache-dir --require-hashes -r /app/requirements.lock

COPY app /app/app
COPY scripts /app/scripts
COPY sql /app/sql
COPY content /app/content

CMD ["python", "-m", "app.main"]
