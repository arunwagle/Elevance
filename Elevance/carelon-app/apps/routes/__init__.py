"""Routes package — Flask blueprints for the Carelon App."""

from routes.auth_routes import auth_bp
from routes.upload_routes import upload_bp
from routes.file_ops_routes import file_ops_bp
from routes.detokenize_routes import detokenize_bp
from routes.admin_routes import admin_bp
from routes.share_routes import share_bp
from routes.volume_api_routes import volume_api_bp

__all__ = [
    'auth_bp', 'upload_bp', 'file_ops_bp',
    'detokenize_bp', 'admin_bp', 'share_bp',
    'volume_api_bp',
]
