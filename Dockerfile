FROM python:3.11-slim

# Set working directory to project root
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc curl \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python dependencies
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy the entire project
COPY . .

# Create the db directory if it doesn't exist
RUN mkdir -p db

# Set environment to production by default (override via env var)
ENV ENVIRONMENT=production
ENV PYTHONUNBUFFERED=1

# Expose port
EXPOSE 8000

# Migrations (postgres mode) + uvicorn. PORT / WEB_CONCURRENCY are honoured for Render/Railway.
WORKDIR /app
CMD ["sh", "/app/scripts/docker/entrypoint.sh"]
