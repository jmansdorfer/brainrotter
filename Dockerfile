FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install uv using pip
RUN pip install uv

# Copy project files
COPY pyproject.toml .

RUN uv pip install --system --no-cache -r pyproject.toml && \
    apt-get update && apt-get install -y gifsicle && rm -rf /var/lib/apt/lists/* && \
    mkdir -p /app/cache/boiler /app/cache/petter /app/temp

# Copy application code
COPY src/ ./src/

# Copy templates (read-only data)
COPY templates/ ./templates/

# Run the bot
CMD ["python", "-m", "src.bot"]