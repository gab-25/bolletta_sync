FROM python:3.13

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY bolletta_agent ./bolletta_agent

CMD ["python", "-m", "bolletta_agent.main"]
