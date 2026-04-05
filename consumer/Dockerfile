FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY config/ config/
COPY consumer/ consumer/
COPY storage/ storage/
COPY .env .env

# Run the consumer
CMD ["python", "-m", "consumer.consumer"]
