FROM python:3.11-slim

WORKDIR /app

# Install dependencies first (cached layer)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy project code
COPY config/ config/
COPY api/ api/
COPY storage/ storage/
COPY .env .env

# Expose the API port
EXPOSE 8000

# Run the API server (no --reload in production)
CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
