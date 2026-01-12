import os

# Flask / JWT
FLASK_SECRET = os.environ.get("FLASK_SECRET", "dev-secret")
JWT_SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "dev-jwt-secret")

# Photo service
PHOTO_SERVICE_URL = os.environ.get(
    "PHOTO_SERVICE_URL",
    "http://photo-service:5003"
)

# Database 
DATABASE_HOST = os.environ.get("DATABASE_HOST")
DATABASE_PORT = os.environ.get("DATABASE_PORT", "3306")
DATABASE_USER = os.environ.get("DATABASE_USER")
DATABASE_PASSWORD = os.environ.get("DATABASE_PASSWORD")
DATABASE_DB_NAME = os.environ.get("DATABASE_DB_NAME")