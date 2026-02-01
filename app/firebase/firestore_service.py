from datetime import datetime
from app.firebase.firebase_admin import FirebaseLoader
from firebase_admin import firestore

class FirestoreService:
    def __init__(self):
        self.db = FirebaseLoader.get_instance()
        self.collection_name = "blogs"
        self.activity_collection = "activities"  # Collection for dashboard feed

    # ---------------- BLOG METHODS ----------------

    def get_blog_by_id(self, blog_id):
        try:
            doc = self.db.collection(self.collection_name).document(blog_id).get()
            if doc.exists:
                data = doc.to_dict()
                data['id'] = doc.id
                return data
            return None
        except Exception as e:
            print(f"❌ Error fetching blog {blog_id}: {e}")
            return None

    def create_draft(self, blog_data, user_id):
        """Saves blog as DRAFT and increments category count."""
        try:
            blog_data['created_at'] = firestore.SERVER_TIMESTAMP
            blog_data['updated_at'] = datetime.utcnow()
            blog_data['author_id'] = user_id

            doc_ref = self.db.collection(self.collection_name).add(blog_data)
            blog_id = doc_ref[1].id

            # Increment category count if exists
            category_name = blog_data.get('category')
            if category_name:
                self.update_category_count(category_name, 1)

            return blog_id
        except Exception as e:
            print(f"❌ Firestore Error creating draft: {e}")
            return None

    def update_blog_status(self, blog_id, status):
        try:
            doc_ref = self.db.collection(self.collection_name).document(blog_id)
            doc_ref.update({
                'status': status.upper(),
                'updated_at': datetime.utcnow()
            })
            return True
        except Exception as e:
            print(f"❌ Error updating status: {e}")
            return False

    def get_blogs_by_status(self, status):
        try:
            docs = self.db.collection(self.collection_name)\
                          .where('status', '==', status.upper()).stream()
            blogs = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                blogs.append(data)
            return blogs
        except Exception as e:
            print(f"❌ Error fetching blogs by status {status}: {e}")
            return []

    def get_total_blogs_count(self):
        """Returns total number of blogs."""
        try:
            count_query = self.db.collection(self.collection_name).count()
            count_result = count_query.get()
            total_count = count_result[0][0].value
            return total_count
        except Exception as e:
            print(f"❌ Error getting total blogs count: {e}")
            return 0

    def get_paginated_drafts(self, page=1, per_page=10):
        try:
            skip = (page - 1) * per_page
            query = self.db.collection(self.collection_name)\
                           .where('status', '==', 'DRAFT')\
                           .order_by('updated_at', direction=firestore.Query.DESCENDING)\
                           .offset(skip)\
                           .limit(per_page)
            
            drafts = []
            for doc in query.stream():
                data = doc.to_dict()
                data['id'] = doc.id
                drafts.append(data)

            # Total draft count
            total_count_query = self.db.collection(self.collection_name)\
                                       .where('status', '==', 'DRAFT')\
                                       .count()
            total_count = total_count_query.get()[0][0].value

            return drafts, total_count
        except Exception as e:
            print(f"❌ Error fetching paginated drafts: {e}")
            return [], 0

    def delete_blog(self, blog_id):
        try:
            blog_ref = self.db.collection(self.collection_name).document(blog_id)
            blog_snap = blog_ref.get()
            if not blog_snap.exists:
                return False

            blog_data = blog_snap.to_dict()
            category_name = blog_data.get("category")

            @firestore.transactional
            def delete_in_transaction(transaction):
                if category_name:
                    cat_query = self.db.collection("categories").where("name", "==", category_name).limit(1)
                    cat_docs = cat_query.get(transaction=transaction)
                    if len(cat_docs) > 0:
                        transaction.update(cat_docs[0].reference, {"count": firestore.Increment(-1)})
                transaction.delete(blog_ref)
                return True

            transaction = self.db.transaction()
            return delete_in_transaction(transaction)
        except Exception as e:
            print(f"❌ Error deleting blog: {e}")
            return False

    # ---------------- CATEGORY METHODS ----------------

    def get_all_categories(self):
        try:
            docs = self.db.collection("categories").stream()
            categories = []
            for doc in docs:
                data = doc.to_dict()
                data['id'] = doc.id
                categories.append(data)
            return categories
        except Exception as e:
            print(f"❌ Error fetching categories: {e}")
            return []

    def update_category_count(self, category_name, increment_by):
        try:
            cat_query = self.db.collection("categories").where("name", "==", category_name).limit(1).get()
            if cat_query:
                cat_ref = cat_query[0].reference
                cat_ref.update({"count": firestore.Increment(increment_by)})
            else:
                self.db.collection("categories").add({
                    "name": category_name,
                    "count": 1 if increment_by > 0 else 0,
                    "created_at": firestore.SERVER_TIMESTAMP
                })
        except Exception as e:
            print(f"❌ Error updating category count: {e}")

    def delete_category(self, category_id):
        try:
            self.db.collection("categories").document(category_id).delete()
            return True
        except Exception as e:
            print(f"❌ Error deleting category: {e}")
            return False

    def update_category(self, category_id, update_data):
        try:
            doc_ref = self.db.collection("categories").document(category_id)
            doc_ref.update(update_data)
            return True
        except Exception as e:
            print(f"❌ Error updating category: {e}")
            return False

    # ---------------- ACTIVITY METHODS ----------------

    def log_activity(self, user, type, action_text, blog_title):
        try:
            doc_ref = self.db.collection(self.activity_collection).document()
            doc_ref.set({
                "user": user,
                "type": type,
                "action_text": action_text,
                "blog_title": blog_title,
                "timestamp": datetime.utcnow(),
                "created_at": firestore.SERVER_TIMESTAMP
            })
            return True
        except Exception as e:
            print(f"❌ Error logging activity: {e}")
            return False

    def get_recent_activity(self, limit=10):
        try:
            docs = (self.db.collection(self.activity_collection)
                        .order_by("timestamp", direction=firestore.Query.DESCENDING)
                        .limit(limit)
                        .stream())
            activities = []
            for doc in docs:
                data = doc.to_dict()
                if 'timestamp' in data:
                    diff = datetime.utcnow() - data['timestamp'].replace(tzinfo=None)
                    if diff.days > 0:
                        data['timestamp'] = f"{diff.days}d ago"
                    elif diff.seconds > 3600:
                        data['timestamp'] = f"{diff.seconds // 3600}h ago"
                    elif diff.seconds > 60:
                        data['timestamp'] = f"{diff.seconds // 60}m ago"
                    else:
                        data['timestamp'] = "Just now"
                activities.append(data)
            return activities
        except Exception as e:
            print(f"❌ Error fetching activities: {e}")
            return []

    # ---------------- USER METHODS ----------------

    def save_user(self, user_data):
        try:
            user_id = user_data.get('uid')
            self.db.collection("users").document(user_id).set({
                "name": user_data.get('name'),
                "email": user_data.get('email'),
                "profile_pic": user_data.get('picture'),
                "last_login": datetime.utcnow()
            }, merge=True)
            return True
        except Exception as e:
            print(f"❌ Error saving user: {e}")
            return False
