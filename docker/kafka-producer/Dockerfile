FROM python:3.11-slim

WORKDIR /app

# Install dependencies
RUN pip install --no-cache-dir kafka-python==2.0.2

COPY kafka_producer.py .

# Data directory — mount your Zeek/Suricata dataset here
VOLUME ["/data"]

ENTRYPOINT ["python", "-u", "kafka_producer.py"]
