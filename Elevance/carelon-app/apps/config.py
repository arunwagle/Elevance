"""Centralized configuration for the Carelon App.

All environment variables and application constants are managed here.
"""

import os


class Config:
    """Base configuration."""

    # --- Unity Catalog Location ---
    CATALOG = os.environ.get('APP_CATALOG', 'aw_serverless_stable_catalog')
    SCHEMA = os.environ.get('APP_SCHEMA', 'carelon')
    VOLUME_NAME = os.environ.get('APP_VOLUME', 'dxutility')

    # Derived Volume root path
    VOLUME_PATH = os.environ.get(
        'VOLUME_PATH',
        f'/Volumes/{CATALOG}/{SCHEMA}/{VOLUME_NAME}'
    )

    # --- Protegrity ---
    PROTEGRITY_API_BASE_URL = os.environ.get('PROTEGRITY_API_BASE_URL', 'http://localhost:5001/api/v1')
    PROTEGRITY_API_TIMEOUT = int(os.environ.get('PROTEGRITY_API_TIMEOUT', '30'))
    PROTEGRITY_API_KEY = os.environ.get('PROTEGRITY_API_KEY', '')

    # --- Upload ---
    MAX_CONTENT_LENGTH = int(os.environ.get('MAX_UPLOAD_SIZE_MB', '2048')) * 1024 * 1024
    ALLOWED_EXTENSIONS = {'csv', 'xlsx', 'xls', 'tsv'}
    UPLOAD_FOLDER = '/tmp/uploads'

    # --- Auth & Session ---
    SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')
    SESSION_TIMEOUT_SECONDS = int(os.environ.get('SESSION_TIMEOUT_SECONDS', '60'))

    # Admin users — these get full admin group permissions
    # Phase 2: Move to Delta table for dynamic management
    ADMIN_USERS = [
        e.strip() for e in
        os.environ.get('ADMIN_USERS', 'arun.wagle@databricks.com').split(',')
    ]

    # --- File Operations ---
    PREVIEW_DEFAULT_ROWS = int(os.environ.get('PREVIEW_DEFAULT_ROWS', '50'))

    # --- Databricks Workspace ---
    DATABRICKS_HOST = os.environ.get('DATABRICKS_HOST', '')


class DevelopmentConfig(Config):
    """Development overrides."""
    DEBUG = True
    SECRET_KEY = 'dev-secret-key-local'


class ProductionConfig(Config):
    """Production overrides."""
    DEBUG = False


def get_config():
    """Return appropriate config based on FLASK_ENV."""
    env = os.environ.get('FLASK_ENV', 'development')
    if env == 'production':
        return ProductionConfig()
    return DevelopmentConfig()
