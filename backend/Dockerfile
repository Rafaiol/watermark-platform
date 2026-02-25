FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install FFmpeg and other necessary system utilities
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements completely
COPY backend/requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source code
COPY backend/ .

# Expose port the app runs on
EXPOSE 8000

# Start FastAPI application with uvicorn and constrain workers
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
