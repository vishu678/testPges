from app.database import db

class Report(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    source = db.Column(db.String(255), nullable=False)
    date_of_retrieval = db.Column(db.DateTime, nullable=False)
    date_of_publication = db.Column(db.String(255), nullable=True)
    url = db.Column(db.String(500), nullable=False, unique=True)
    company = db.Column(db.String(255), nullable=True)
    content = db.Column(db.Text, nullable=True)
    keyword = db.Column(db.String(255), nullable=True)
    content_type = db.Column(db.String(255), nullable=True)
    summary = db.Column(db.Text, nullable=True)
    title = db.Column(db.String(500), nullable=True)

    def __repr__(self):
        return f"<Report {self.source} - {self.url}>"

class ESGImage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    report_url = db.Column(db.String(500), nullable=False)
    page_number = db.Column(db.Integer, nullable=False)
    keyword = db.Column(db.String(255), nullable=True)
    image_data = db.Column(db.LargeBinary, nullable=False)  # Store image binary
    content_type = db.Column(db.String(50), default="image/png")

    def __repr__(self):
        return f"<Image from page {self.page_number} - {self.keyword}>"

