import os


APP_NAME = "GreenPulse AI"

DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("GREENPULSE_CORS_ORIGINS", DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]
