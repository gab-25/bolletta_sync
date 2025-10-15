FROM python:3.13

ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bolletta_sync ./bolletta_sync

CMD ["python", "-m", "uvicorn", "bolletta_sync.main:app"]
