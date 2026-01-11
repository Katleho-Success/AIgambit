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

# Copy and make startup script executable
COPY start.sh .
RUN chmod +x start.sh

# Run the application
CMD ["./start.sh"]
