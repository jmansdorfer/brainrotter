FROM python:3.12-slim

# Set working directory
WORKDIR /app

# Install uv using pip
RUN pip install uv

# Copy project files
COPY pyproject.toml .
COPY main.py .
COPY data/template_boiling.gif .

# Install dependencies using uv
RUN uv pip install --system -r pyproject.toml

# Create temp directory for bot operations
RUN mkdir -p temp

# Run the bot
CMD ["python", "main.py"]