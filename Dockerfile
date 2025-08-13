FROM python:3.13

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY my_agent ./my_agent

CMD ["python", "-m", "my_agent.main"]
