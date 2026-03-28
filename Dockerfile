FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY pyproject.toml .

RUN pip install --no-cache-dir .

RUN python -m playwright install --with-deps chromium

COPY ./bolletta_sync ./bolletta_sync

CMD ["fastapi", "run"]
