"""Carelon App — Flask application entry point.

Factory pattern creates and configures the app with modular blueprints.
"""

import os
import logging
from flask import Flask, redirect, url_for, session, render_template

from config import get_config

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def create_app():
    """Application factory — creates and configures the Flask app."""
    app = Flask(__name__)

    # Load configuration
    config = get_config()
    app.config.from_object(config)

    # Ensure upload directory exists
    os.makedirs(app.config.get('UPLOAD_FOLDER', '/tmp/uploads'), exist_ok=True)

    # --- Register Blueprints ---
    from routes.auth_routes import auth_bp
    from routes.upload_routes import upload_bp
    from routes.file_ops_routes import file_ops_bp
    from routes.detokenize_routes import detokenize_bp
    from routes.admin_routes import admin_bp
    from routes.share_routes import share_bp
    from routes.volume_api_routes import volume_api_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(upload_bp)
    app.register_blueprint(file_ops_bp)
    app.register_blueprint(detokenize_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(share_bp)
    app.register_blueprint(volume_api_bp)

    # --- Root & Utility Routes ---
    @app.route('/')
    def index():
        """Redirect to dashboard or login based on session."""
        if session.get('user_id'):
            return redirect(url_for('dashboard'))
        return redirect(url_for('auth.login'))

    @app.route('/dashboard')
    def dashboard():
        """Welcome / landing page after login."""
        if not session.get('user_id'):
            return redirect(url_for('auth.login'))
        return render_template(
            'dashboard.html',
            username=session.get('display_name', session.get('username', 'User')),
            email=session.get('email', ''),
            groups=session.get('groups', []),
            permissions=session.get('permissions', []),
        )

    @app.route('/health')
    def health():
        """Health check for Databricks App monitoring."""
        return {'status': 'healthy', 'app': 'carelon-app'}, 200

    # --- Error Handlers ---
    @app.errorhandler(401)
    def unauthorized(e):
        return redirect(url_for('auth.login'))

    @app.errorhandler(403)
    def forbidden(e):
        return {'error': 'Access denied. Insufficient permissions.'}, 403

    @app.errorhandler(413)
    def too_large(e):
        return {'error': 'File too large. Maximum upload size is 2 GB.'}, 413

    @app.errorhandler(500)
    def internal_error(e):
        logger.error(f"Internal server error: {e}")
        return {'error': 'Internal server error occurred.'}, 500

    logger.info("Carelon App initialized successfully.")
    return app


# Create app instance (gunicorn entry: app:app)
app = create_app()

if __name__ == '__main__':
    port = int(os.environ.get('DATABRICKS_APP_PORT', 8000))
    app.run(host='0.0.0.0', port=port, debug=False)
