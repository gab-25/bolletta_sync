FROM python:3.13

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bolletta_sync ./bolletta_sync

CMD ["python", "-m", "bolletta_sync.main"]
