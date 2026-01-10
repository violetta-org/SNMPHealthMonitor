
from app import app, db
from db.models import User
from werkzeug.security import generate_password_hash

with app.app_context():
    # Check if user exists
    user = User.query.filter_by(username='admin').first()
    if not user:
        print("Creating admin user...")
        hashed_pw = generate_password_hash('admin')
        new_user = User(username='admin', password=hashed_pw)
        db.session.add(new_user)
        db.session.commit()
        print("User 'admin' created with password 'admin'")
    else:
        print("User 'admin' already exists.")
        # Optional: Reset password if you want
        # user.password = generate_password_hash('admin')
        # db.session.commit()
        # print("Password reset to 'admin'")
