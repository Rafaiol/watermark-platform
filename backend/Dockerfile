FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install FFmpeg and other necessary system utilities
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements completely
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the backend source code
COPY . .

# Expose port the app runs on
EXPOSE 8000

# Start FastAPI application with uvicorn and constrain workers. Use $PORT provided by Railway/Render
CMD ["sh", "-c", "uvicorn main:app --host 0.0.0.0 --port ${PORT:-8000} --workers 1"]
