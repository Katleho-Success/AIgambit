#!/usr/bin/env python3
"""Entry point for Railway deployment"""
import os
import sys

if __name__ == "__main__":
    port = os.environ.get("PORT", "8080")
    print(f"Starting server on port {port}")
    
    # Start gunicorn with the correct port
    os.execvp("gunicorn", [
        "gunicorn",
        "--worker-class", "eventlet",
        "-w", "1",
        "--bind", f"0.0.0.0:{port}",
        "app:app"
    ])
