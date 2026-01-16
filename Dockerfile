FROM python:3.13-slim

# Set working directory
WORKDIR /app

# Install uv using pip
RUN pip install uv

# Copy project files
COPY pyproject.toml .

# Install dependencies using uv
RUN uv pip install --system --no-cache -r pyproject.toml

# Copy application code
COPY src/ ./src/

# Copy templates (read-only data)
COPY templates/ ./templates/

# Create temp directory for bot operations
RUN mkdir -p /app/cache/boiler /app/cache/petter /app/temp

# Run the bot
CMD ["python", "-m", "src.bot"]