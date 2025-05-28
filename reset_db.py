from app import create_app
from app.database import db
from app.models import Report, ESGImage  # import all models

app = create_app()

with app.app_context():
    db.drop_all()
    db.create_all()
    print("✅ Database schema reset successfully.")
