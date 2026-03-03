FROM python:3.13-slim

WORKDIR /app

# Install uv using pip
RUN pip install uv

# Copy project files
COPY pyproject.toml .

RUN uv pip install --system --no-cache -r pyproject.toml && \
    apt-get update && apt-get install -y gifsicle && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /app/cache/boiler /app/cache/petter /app/cache/framemog /app/temp

# Copy application code
COPY src/ ./src/

# Copy templates (read-only data)
COPY templates/ ./templates/

CMD ["python", "-m", "src.bot"]
