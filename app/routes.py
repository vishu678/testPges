from flask import Blueprint, jsonify, send_file
from app.database import db
from app.models import ESGImage
import io
from app.models import Report
from flask import render_template
from collections import defaultdict
import os
import random
from flask import current_app as app
from flask import send_from_directory, current_app as app

api = Blueprint("api", __name__)

@api.route("/", methods=["GET"])
def home():
    return jsonify({"message": "Welcome to ESG AIoT Crawler API!"})

@api.route("/image/<int:image_id>", methods=["GET"])
def get_image(image_id):
    img = ESGImage.query.get(image_id)
    if not img:
        return jsonify({"error": "Image not found"}), 404

    return send_file(
        io.BytesIO(img.image_data),
        mimetype=f"image/{img.content_type}",
        download_name=f"esg_image_{image_id}.{img.content_type}"
    )

@api.route("/summary/<int:report_id>", methods=["GET"])
def get_summary(report_id):
    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404
    return jsonify({
        "company": report.company,
        "source": report.source,
        "summary": report.summary or "No summary generated yet."
    })

@api.route("/reports/<int:report_id>", methods=["GET"])
def get_report_details(report_id):
    report = Report.query.get(report_id)
    if not report:
        return jsonify({"error": "Report not found"}), 404

    return jsonify({
        "id": report.id,
        "source": report.source,
        "company": report.company,
        "date_of_retrieval": report.date_of_retrieval.strftime("%Y-%m-%d %H:%M:%S"),
        "date_of_publication": report.date_of_publication,
        "url": report.url,
        "content_type": report.content_type,
        "keyword": report.keyword,
        "summary": report.summary,
        "content": report.content[:2000] + "..." if report.content and len(report.content) > 2000 else report.content
    })

@api.route("/reports", methods=["GET"])
def get_all_reports():
    reports = Report.query.order_by(Report.date_of_retrieval.desc()).all()
    return jsonify([
        {
            "id": report.id,
            "source": report.source,
            "company": report.company,
            "date_of_retrieval": report.date_of_retrieval.strftime("%Y-%m-%d %H:%M:%S"),
            "date_of_publication": report.date_of_publication,
            "url": report.url,
            "content_type": report.content_type,
            "keyword": report.keyword,
            "has_summary": bool(report.summary),
        }
        for report in reports
    ])

@api.route("/summaries/recent", methods=["GET"])
def get_recent_summaries():
    from datetime import datetime, timedelta
    cutoff = datetime.utcnow() - timedelta(days=1)

    reports = Report.query.filter(Report.date_of_retrieval >= cutoff).all()

    return jsonify([
        {
            "title": r.source,
            "date": r.date_of_publication,
            "company": r.company,
            "url": r.url,
            "summary": r.summary
        }
        for r in reports if r.summary
    ])

#Previous function to display summaries form images extrcated from the article.
""" @api.route('/summaries')
def summaries():
    reports = Report.query.filter(Report.summary != None).order_by(Report.date_of_publication.desc()).limit(20).all()
    images = ESGImage.query.filter(ESGImage.report_url.in_([r.url for r in reports])).all()

    images_by_url = defaultdict(list)
    for img in images:
        images_by_url[img.report_url].append(img)

    return render_template("summaries.html", summaries=reports, images_by_url=images_by_url) """

@api.route('/iaq_gallery/<path:filename>')
def serve_gallery_image(filename):
    return send_from_directory(os.path.join(app.root_path, 'images'), filename)

# New function to display summaries from a set of images randomize for each article.
@api.route('/summaries')
def summaries():
    reports = Report.query.filter(Report.summary != None).order_by(Report.date_of_publication.desc()).limit(20).all()

    # Load random images from app/images/
    image_dir = os.path.join(app.root_path, 'images')
    image_files = [f for f in os.listdir(image_dir) if f.lower().endswith(('.png', '.jpg', '.jpeg', '.webp'))]
    random.shuffle(image_files)

    # Assign one random image per summary
    static_images = {}
    for i, report in enumerate(reports):
        static_images[report.url] = image_files[i % len(image_files)]

    return render_template("summaries.html", summaries=reports, static_images=static_images)


