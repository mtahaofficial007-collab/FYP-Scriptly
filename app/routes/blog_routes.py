from flask import Blueprint, render_template, request, jsonify, url_for, session, redirect
from app.agents.blog_agent import BlogAgent
from app.agents.drafts_agent import DraftsAgent
from app.agents.category_agent import CategoryAgent
from app.agents.approval_agent import ApprovalAgent
from app.firebase.firestore_service import FirestoreService
from datetime import datetime
import math

blog_bp = Blueprint('blog', __name__)
db_service = FirestoreService()

# --- SECURITY MIDDLEWARE ---

@blog_bp.before_request
def require_login():
    """Redirects to login if user session is not active."""
    # This ensures that even if a user types /dashboard or /create manually, 
    # they are kicked back to the login page if not authenticated.
    if not session.get('logged_in'):
        return redirect(url_for('auth_bp.login'))

# --- WEB PAGE ROUTES ---

@blog_bp.route('/dashboard')
def home():
    """Renders Dashboard with real-time Firestore stats and Activity Feed."""
    try:
        hour = datetime.now().hour
        greeting = "Good Morning" if hour < 12 else "Good Afternoon" if hour < 18 else "Good Evening"
        username = session.get('user_name', 'Admin')

        total_blogs = db_service.get_total_blogs_count()
        drafts = db_service.get_blogs_by_status("DRAFT")
        pending = db_service.get_blogs_by_status("UNDER_REVIEW")
        categories = db_service.get_all_categories()
        recent_activity = db_service.get_recent_activity(limit=10)
        
        return render_template('home.html', 
                               greeting=greeting,
                               username=username,
                               total_blogs_count=total_blogs,
                               drafts_count=len(drafts), 
                               pending_count=len(pending),
                               categories_count=len(categories),
                               recent_activity=recent_activity)
    except Exception as e:
        print(f"Error in home route: {e}")
        return render_template('home.html', total_blogs_count=0, recent_activity=[])

@blog_bp.route('/create')
def create_page():
    username = session.get('user_name', 'Admin')
    return render_template('create_blog.html', username=username)

@blog_bp.route('/edit/<blog_id>')
def edit_blog(blog_id):
    """Renders the editor for a specific blog."""
    username = session.get('user_name', 'Admin')
    blog_data = db_service.get_blog_by_id(blog_id)
    if not blog_data:
        return "Blog not found", 404
    return render_template('edit_blog.html', blog=blog_data, username=username)

@blog_bp.route('/drafts')
def drafts_page():
    page = request.args.get('page', 1, type=int)
    per_page = 10 
    drafts, total_count = db_service.get_paginated_drafts(page=page, per_page=per_page)
    total_pages = math.ceil(total_count / per_page)
    
    return render_template(
        'drafts.html', 
        drafts=drafts, 
        current_page=page, 
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )
    
@blog_bp.route('/approval')
def approval_page():
    """Renders the Admin Approval page with blogs status 'UNDER_REVIEW'."""
    page = request.args.get('page', 1, type=int)
    per_page = 10
    
    all_pending = db_service.get_blogs_by_status("UNDER_REVIEW")
    total_count = len(all_pending)
    total_pages = math.ceil(total_count / per_page)
    
    start = (page - 1) * per_page
    end = start + per_page
    pending_blogs = all_pending[start:end]
    
    return render_template(
        'approval_queue.html', 
        pending_blogs=pending_blogs, 
        current_page=page, 
        total_pages=total_pages,
        has_next=page < total_pages,
        has_prev=page > 1
    )

@blog_bp.route('/categories')
def categories_page():
    categories = db_service.get_all_categories()
    return render_template('categories.html', categories=categories)

# --- API ACTION ENDPOINTS ---

@blog_bp.route('/api/generate', methods=['POST'])
def generate_and_submit():
    """AI Content Generation Pipeline with Intelligent Categorization."""
    try:
        data = request.get_json()
        prompt = data.get('prompt')
        auto_submit = data.get('auto_submit', False)
        
        blog_ai = BlogAgent()
        generated_data = blog_ai.run_pipeline(prompt)
        
        cat_agent = CategoryAgent()
        content_text = generated_data.get('content', {}).get('body', '')
        assigned_cat = cat_agent.categorize_blog(generated_data.get('title'), content_text)
        generated_data['category'] = assigned_cat
        
        draft_agent = DraftsAgent()
        status = "UNDER_REVIEW" if auto_submit else "DRAFT"
        generated_data['status'] = status
        
        user_id = session.get('user_id', 'system_gen')
        blog_id = draft_agent.create_initial_draft(generated_data, user_id)
        
        db_service.log_activity(
            user=session.get('user_name', 'Admin'),
            type="generated",
            action_text=f"generated a blog in {assigned_cat}",
            blog_title=generated_data.get('title', 'Untitled')
        )
        
        return jsonify({
            "success": True, 
            "redirect": url_for('blog.approval_page' if auto_submit else 'blog.drafts_page') 
        }), 201
    except Exception as e:
        print(f"❌ Route Error in Generate: {e}")
        return jsonify({"success": False, "error": str(e)}), 500

@blog_bp.route('/api/update_status/<blog_id>', methods=['POST'])
def update_status(blog_id):
    """General status update (Approving or Rejecting)."""
    try:
        data = request.get_json()
        new_status = data.get('status', 'DRAFT')
        success = db_service.update_blog_status(blog_id, new_status)
        
        if success:
            blog_data = db_service.get_blog_by_id(blog_id)
            action_text = "rejected back to drafts" if new_status == "DRAFT" else "approved for publication"
            db_service.log_activity(
                user=session.get('user_name', 'Admin'),
                type="edited" if new_status == "DRAFT" else "published",
                action_text=action_text,
                blog_title=blog_data.get('title', 'Untitled') if blog_data else "Untitled"
            )
            
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@blog_bp.route('/api/submit_for_review/<blog_id>', methods=['POST'])
def submit_for_review(blog_id):
    """Manual trigger to move blog from DRAFT to UNDER_REVIEW."""
    success = db_service.update_blog_status(blog_id, "UNDER_REVIEW")
    if success:
        blog_data = db_service.get_blog_by_id(blog_id)
        db_service.log_activity(
            user=session.get('user_name', 'Admin'),
            type="review_requested",
            action_text="submitted for approval",
            blog_title=blog_data.get('title', 'Untitled') if blog_data else "Untitled"
        )
    return jsonify({"success": success, "redirect": url_for('blog.home')})

@blog_bp.route('/api/delete_blog/<blog_id>', methods=['DELETE'])
def delete_blog_api(blog_id):
    """Permanently removes a blog and logs activity."""
    blog_data = db_service.get_blog_by_id(blog_id)
    title = blog_data.get('title', 'Untitled') if blog_data else "Untitled"
    
    success = db_service.delete_blog(blog_id)
    if success:
        db_service.log_activity(
            user=session.get('user_name', 'Admin'),
            type="deleted",
            action_text="permanently deleted",
            blog_title=title
        )
    return jsonify({"success": success})

@blog_bp.route('/api/delete_category/<category_id>', methods=['DELETE'])
def delete_category_api(category_id):
    """Deletes a category and logs activity."""
    try:
        categories = db_service.get_all_categories()
        category = next((c for c in categories if c.get('id') == category_id), None)
        cat_name = category.get('name', 'Unknown') if category else "Unknown"

        success = db_service.delete_category(category_id)
        
        if success:
            db_service.log_activity(
                user=session.get('user_name', 'Admin'),
                type="deleted",
                action_text="deleted the category",
                blog_title=cat_name
            )
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@blog_bp.route('/api/edit_category/<category_id>', methods=['POST'])
def edit_category_api(category_id):
    """Updates a category name and logs activity."""
    try:
        data = request.get_json()
        new_name = data.get('name')
        
        if not new_name:
            return jsonify({"success": False, "error": "Name is required"}), 400

        success = db_service.update_category(category_id, {"name": new_name})
        
        if success:
            db_service.log_activity(
                user=session.get('user_name', 'Admin'),
                type="edited",
                action_text="renamed a category to",
                blog_title=new_name
            )
        return jsonify({"success": success})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500