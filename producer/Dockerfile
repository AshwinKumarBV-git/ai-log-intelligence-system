FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY config/ config/
COPY producer/ producer/
COPY .env .env

# Run the producer
CMD ["python", "-m", "producer.producer"]
