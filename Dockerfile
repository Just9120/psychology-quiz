FROM python:3.12-slim

ARG APP_REVISION=UNSET
LABEL org.opencontainers.image.revision=$APP_REVISION
ENV APP_REVISION=$APP_REVISION

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY scripts /app/scripts
COPY sql /app/sql
COPY content /app/content

CMD ["python", "-m", "app.main"]
