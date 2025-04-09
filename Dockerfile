FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY main.py main.py
COPY config.yaml config.yaml

CMD ["python", "main.py"]