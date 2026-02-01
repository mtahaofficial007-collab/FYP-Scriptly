import os
from flask import Flask, redirect, url_for, session
from config import Config
from app.firebase.firebase_admin import FirebaseLoader
from whitenoise import WhiteNoise
from werkzeug.middleware.proxy_fix import ProxyFix

def create_app(config_class=Config):
    app = Flask(__name__,
                static_folder='static',
                template_folder='templates')
    
    app.config.from_object(config_class)

    # 1. FIX: Ensure Flask knows it's behind a WSGI server
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1)

    # 2. WHITENOISE: Serve static files directly and efficiently
    # The root should point to where your 'static' folder is located
    app.wsgi_app = WhiteNoise(app.wsgi_app, root='app/static/', prefix='static/')

    # Initialize Firebase
    FirebaseLoader.get_instance(
        app.config['FIREBASE_SERVICE_ACCOUNT']
    )

    @app.route('/')
    def index():
        if not session.get('logged_in'):
            return redirect(url_for('auth_bp.login'))
        return redirect(url_for('blog.home'))

    # Register Blueprints
    from app.routes.blog_routes import blog_bp
    app.register_blueprint(blog_bp)

    from app.routes.auth import auth_bp
    app.register_blueprint(auth_bp)
        
    return app