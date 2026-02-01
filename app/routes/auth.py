from flask import Blueprint, render_template, request, jsonify, session, redirect, url_for, current_app
from firebase_admin import auth as admin_auth
from app.firebase.firestore_service import FirestoreService

auth_bp = Blueprint('auth_bp', __name__)
db_service = FirestoreService()

@auth_bp.route('/login', methods=['GET', 'POST'])
def login():
    if session.get('logged_in'):
        return redirect(url_for('blog.home'))
    return render_template('login.html', firebase_config=current_app.config['FIREBASE_CONFIG'])

@auth_bp.route('/signup', methods=['GET', 'POST'])
def signup():
    if session.get('logged_in'):
        return redirect(url_for('blog.home'))
    return render_template('signup.html', firebase_config=current_app.config['FIREBASE_CONFIG'])

@auth_bp.route('/api/auth/verify', methods=['POST'])
def verify_token():
    """Universal verification for both Google and Manual Email logins."""
    data = request.json
    id_token = data.get('idToken')
    try:
        decoded_token = admin_auth.verify_id_token(id_token)
        uid = decoded_token['uid']
        
        user_info = {
            "uid": uid,
            "name": decoded_token.get('name') or decoded_token.get('email').split('@')[0],
            "email": decoded_token.get('email'),
            "picture": decoded_token.get('picture', '')
        }

        # Save to Firestore
        db_service.save_user(user_info)

        # Set Session and Redirect to Dashboard
        session.permanent = True
        session.update({
            'user_id': uid,
            'user_name': user_info['name'],
            'logged_in': True
        })

        # CRITICAL: Redirect to blog.home (Dashboard)
        return jsonify({"success": True, "redirect": url_for('blog.home')})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 401

@auth_bp.route('/logout')
def logout():
    session.clear()
    # Explicitly tell the session it has been modified
    session.modified = True 
    return redirect(url_for('auth_bp.login'))