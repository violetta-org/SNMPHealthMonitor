FROM python:3.10-slim

WORKDIR /app

# Install system dependencies if any are needed (e.g., netcat/curl for testing/healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy and install python dependencies
COPY db_worker/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy worker code and reuse the rasberrypi db services
COPY db_worker/ /app/db_worker/
COPY rasberrypi/db_service/ /app/rasberrypi/db_service/
COPY rasberrypi/utils/ /app/rasberrypi/utils/
COPY rasberrypi/units.py /app/rasberrypi/units.py

# Add app paths to python path
ENV PYTHONPATH=/app:/app/rasberrypi

# Run the UDP worker
CMD ["python", "-u", "db_worker/worker.py"]
