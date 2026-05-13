FROM python:3.12-slim

LABEL maintainer="Jane-o-O-o-O"
LABEL description="EvalArena - LLM Evaluation Arena"

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml README.md ./
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Create data directory for SQLite database
RUN mkdir -p /data

# Expose the default port
EXPOSE 8080

# Default command
ENTRYPOINT ["evalarena"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8080", "--db", "/data/evalarena.db"]
