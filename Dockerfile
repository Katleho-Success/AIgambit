# Use Python slim image with Stockfish
FROM python:3.11-slim

# Install Stockfish chess engine
RUN apt-get update && apt-get install -y \
    stockfish \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy requirements first for caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8080

# Set environment variable for Stockfish path
ENV STOCKFISH_PATH=/usr/games/stockfish

# Run the application using Python to handle PORT
CMD python -c "import os; port = os.environ.get('PORT', '8080'); import subprocess; subprocess.run(['gunicorn', '--worker-class', 'eventlet', '-w', '1', '--bind', f'0.0.0.0:{port}', 'app:app'])"
