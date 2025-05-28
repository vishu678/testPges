import os
import sys
import time
import requests
import spacy
from bs4 import BeautifulSoup
from flask import Flask
from datetime import datetime, timedelta
import json
import subprocess
from googlesearch import search
import feedparser
from urllib.parse import urlparse
from app.models import ESGImage, Report
from app import create_app
from app.database import db
import re
import textwrap
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

nlp = spacy.load("en_core_web_sm")
app = create_app()

LOOKBACK_DAYS = 0

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.5",
    "Referer": "https://www.google.com/",
}

FIRST_PRIORITY_KEYWORDS = [
    "indoor air quality", 
    "internet of things and air", 
    "AIoT air monitoring",
    "environmental sensors for air quality"
]

SECOND_PRIORITY_KEYWORDS = [
    "IoT", "air quality", "AI", "AIoT", "emissions", 
    "smart devices", "HVAC", "environmental monitoring", 
    "sustainability", "ESG", "carbon footprint"
]

def match_priority_keywords(text):
    text_lower = text.lower()
    first_hits = [kw for kw in FIRST_PRIORITY_KEYWORDS if kw.lower() in text_lower]
    if first_hits:
        return first_hits, "first"
    second_hits = [kw for kw in SECOND_PRIORITY_KEYWORDS if kw.lower() in text_lower]
    if second_hits:
        return second_hits, "second"
    return [], None

def ensure_ollama_running():
    try:
        response = requests.get("http://localhost:11434/api/tags", timeout=2)
        return response.status_code == 200
    except:
        print("🚀 Starting Ollama server...")
        subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(5)
        return True

def format_summary_text(raw_summary: str) -> str:
    if not raw_summary:
        return ""

    # Step 1: Convert markdown-style bold headers to H3 tags
    formatted = re.sub(r"\*\*(.*?)\*\*", r"\n\n\1:\n", raw_summary)

    # Step 2: Break by paragraphs
    parts = [p.strip() for p in formatted.split("\n\n") if p.strip()]

    html_parts = []
    inside_list = False

    for part in parts:
        if part.endswith(":"):
            # Render headings as <h3>
            if inside_list:
                html_parts.append("</ul>")
                inside_list = False
            html_parts.append(f"<h3>{part[:-1].strip()}</h3>")  # remove colon
        elif part.startswith("- ") or part.startswith("• "):
            # Start unordered list
            if not inside_list:
                html_parts.append("<ul>")
                inside_list = True
            # Add list item(s)
            for line in part.splitlines():
                line = line.strip()
                if line.startswith("- ") or line.startswith("• "):
                    html_parts.append(f"<li>{line[2:].strip()}</li>")
        else:
            if inside_list:
                html_parts.append("</ul>")
                inside_list = False
            # Wrap paragraph
            chunks = textwrap.wrap(part, width=600)
            for chunk in chunks:
                html_parts.append(f"<p>{chunk.strip()}</p>")

    if inside_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)

def generate_title_from_summary(summary, model="mistral"):
    print("🧠 Generating title from summary...")
    ensure_ollama_running()
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": f"""
        Based on the following ESG summary, write a concise, informative, and SEO-friendly title (10 words max).
        Do not include quotes or your own commentary.

        --- SUMMARY ---
        {summary}
        --- END ---
        """,
        "stream": False
    }
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload))
        if response.status_code == 200:
            return response.json().get("response", "").strip().replace('"', '')
        else:
            print(f"❌ Ollama title API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ollama title connection failed: {e}")
        return None


def generate_summary_with_ollama(content, model="mistral"):
    print("🧠 Generating summary using Ollama...")
    ensure_ollama_running()
    url = "http://localhost:11434/api/generate"
    payload = {
        "model": model,
        "prompt": f"""
        You are a professional ESG analyst. Write a detailed half-page summary (at least 300 words) based on the following ESG report content.

        Focus on:
        - Environmental protection efforts
        - Indoor air quality and emissions reduction
        - Energy efficiency and HVAC improvements
        - Corporate sustainability goals and progress

        Do not ask questions or introduce yourself. Just provide a well-structured, concise but rich summary using paragraphs.

        --- BEGIN REPORT ---
        {content}
        --- END REPORT ---
        """,
        "stream": False
    }
    try:
        response = requests.post(url, headers={"Content-Type": "application/json"}, data=json.dumps(payload))
        if response.status_code == 200:
            return response.json().get("response", "").strip()
        else:
            print(f"❌ Ollama API error: {response.status_code}")
            return None
    except Exception as e:
        print(f"❌ Ollama connection failed: {e}")
        return None

def discover_urls_from_keywords(keywords, num_results=5):
    query = " ".join(keywords)
    try:
        return list(search(query, num_results=num_results))
    except Exception as e:
        print(f"❌ Google search failed: {e}")
        return []

def extract_text_from_url(url, timeout=30):
    try:
        response = requests.get(url, headers=HEADERS, timeout=timeout)
        response.raise_for_status()
        html = response.content
        soup = BeautifulSoup(html, "html.parser")
        text = "\n".join([p.text.strip() for p in soup.find_all("p") if len(p.text.strip()) > 40])
        return text, html
    except Exception as e:
        print(f"❌ Failed to extract from {url}: {e}")
        return None, None

def fetch_rss_articles(feed_url, days_back=LOOKBACK_DAYS):
    feed = feedparser.parse(feed_url)
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    articles = []
    for entry in feed.entries:
        if hasattr(entry, "published_parsed") and entry.published_parsed:
            dt = datetime(*entry.published_parsed[:6])
            if dt >= cutoff:
                articles.append({"title": entry.title, "url": entry.link, "published": dt.strftime('%Y-%m-%d')})
    return articles

def extract_company_name_from_url(html, url):
    if not html:
        return "General"
    soup = BeautifulSoup(html, "html.parser")
    og = soup.find("meta", property="og:site_name")
    if og and og.get("content"):
        return og["content"].strip()
    author = soup.find("meta", attrs={"name": "author"})
    if author and author.get("content"):
        return author["content"].strip()
    if soup.title and soup.title.string:
        title = soup.title.string.strip()
        if "-" in title: return title.split("-")[-1].strip()
        if "|" in title: return title.split("|")[-1].strip()
        return title
    return urlparse(url).netloc.replace("www.", "").split(".")[0].capitalize()

def extract_and_store_images(url, keyword):
    try:
        response = requests.get(url, headers=HEADERS, timeout=20)
        soup = BeautifulSoup(response.content, "html.parser")
        img_tags = soup.find_all("img")
        for i, img in enumerate(img_tags):
            src = img.get("src")
            if not src or not src.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
                continue
            if src.startswith("//"):
                src = "https:" + src
            elif src.startswith("/"):
                base = "/".join(url.split("/")[:3])
                src = base + src
            try:
                img_resp = requests.get(src, timeout=10)
                if img_resp.status_code == 200:
                    db.session.add(ESGImage(
                        report_url=url,
                        page_number=i + 1,
                        keyword=keyword,
                        image_data=img_resp.content,
                        content_type=img_resp.headers.get("Content-Type", "image/png")
                    ))
            except Exception as e:
                print(f"⚠️ Failed image: {src} — {e}")
        db.session.commit()
    except Exception as e:
        print(f"❌ Image extraction failed: {e}")

def run_scraper():
    with app.app_context():
        added_count = 0
        rss_added = 0
        cutoff_date = datetime.now(timezone.utc) - timedelta(days=LOOKBACK_DAYS)

        print("🌐 Discovering Google articles...")
        discovered = []
        for kw in FIRST_PRIORITY_KEYWORDS:
            discovered += discover_urls_from_keywords([kw], num_results=3)
        if len(discovered) < 5:
            for kw in SECOND_PRIORITY_KEYWORDS:
                discovered += discover_urls_from_keywords([kw], num_results=2)
        discovered = list(set(discovered))

        for url in discovered:
            existing = Report.query.filter_by(url=url).first()
            if existing:
                print(f"⏭️ Skipping Google article already in database: {url}")
                continue

            print(f"\n🆕 New Google article found: {url}")
            content, raw_html = extract_text_from_url(url)
            if not content:
                continue

            company = extract_company_name_from_url(raw_html, url)
            keywords, level = match_priority_keywords(content)
            if not keywords:
                print(f"[❌ SKIP] No matching keywords found for: {url}")
                continue

            raw_summary = generate_summary_with_ollama(content[:5000])
            summary = format_summary_text(raw_summary)

            title = generate_title_from_summary(summary) if summary else None

            db.session.add(Report(
                source="Web Article",
                date_of_retrieval=datetime.now(timezone.utc),
                date_of_publication=datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                url=url,
                company=company,
                keyword=", ".join(keywords),
                content_type="Web Article",
                content=content,
                summary=summary,
                title=title
            ))
            db.session.commit()
            added_count += 1

            print(f"[✅ SAVED] Google article saved")
            extract_and_store_images(url, ", ".join(keywords))

        print("🌐 Fetching RSS feeds...")
        rss_feeds = [
            "https://news.google.com/rss/search?q=ESG+air+quality",
            "https://www.environmentalleader.com/feed/",
            "https://cleantechnica.com/feed/",
            "https://esgtoday.com/feed",
            "https://knowesg.com/rss.xml",
            "https://esgpro.co.uk/feed",
            "https://advanceesg.org/feed",
            "https://www.esginvestor.net/feed",
            "https://airqualitynews.com/feed",
            "https://www.sciencedaily.com/rss/earth_climate/air_quality.xml",
            "https://smartairfilters.com/en/feed",
            "https://www.epa.gov/indoorairplus/indoor-airplus-mobile-app-rss-podcast-feed-xml-file",
            "https://www.greenbuildermedia.com/healthy-homes-indoor-air-quality-subscription-page"
        ]

        rss_skip_days = 3
        rss_cutoff = datetime.now(timezone.utc) - timedelta(days=rss_skip_days)

        for feed in rss_feeds:
            feed_domain = urlparse(feed).netloc.replace("www.", "").split("/")[0]

            recent_articles = Report.query.filter(
                Report.source == "RSS Feed",
                Report.url.contains(feed_domain),
                Report.date_of_retrieval >= rss_cutoff
            ).first()

            if recent_articles:
                print(f"⏭️ Skipping {feed} (already used within last {rss_skip_days} days)")
                continue

            for article in fetch_rss_articles(feed, days_back=LOOKBACK_DAYS):
                url = article["url"]
                existing = Report.query.filter_by(url=url).first()
                if existing:
                    print(f"⏭️ Skipping RSS article already in database: {url}")
                    continue

                print(f"\n🆕 New RSS article found: {url}")
                content, raw_html = extract_text_from_url(url)
                if not content:
                    continue

                company = extract_company_name_from_url(raw_html, url)
                keywords, level = match_priority_keywords(content)
                if not keywords:
                    print(f"❌ Skipping No matching keywords found for: {url}")
                    continue

                raw_summary = generate_summary_with_ollama(content[:5000])
                summary = format_summary_text(raw_summary) if len(content) > 1000 else None
                title = generate_title_from_summary(summary) if summary else None

                db.session.add(Report(
                    source="RSS Feed",
                    date_of_retrieval=datetime.now(timezone.utc),
                    date_of_publication=article["published"],
                    url=url,
                    company=company,
                    keyword=", ".join(keywords),
                    content_type="Web Article",
                    content=content,
                    summary=summary,
                    title=title
                ))
                db.session.commit()
                rss_added += 1

                print(f"✅ RSS article saved")
                extract_and_store_images(url, ", ".join(keywords))

        print("✅ Web Scraping Done")
        print(f"📊 Google → Added: {added_count}")
        print(f"📡 RSS    → Added: {rss_added}")

if __name__ == "__main__":
    run_scraper()
# Auto-push updated summary.html to GitHub
    try:
        print("📤 Committing Changes to GitHub...")
        repo_path = "/Users/vishvakumar/esg_iaq_auto_blog"  # ← Replace with your actual repo path
        os.chdir(repo_path)

        subprocess.run(["git", "add", "."], check=True)
        subprocess.run(["git", "commit", "-m", "Auto update from scraper"], check=True)
        subprocess.run(["git", "push"], check=True)
        print("✅ Git push successful.")
    except subprocess.CalledProcessError as e:
        print(f"❌ Git push failed: {e}")
    except Exception as e:
        print(f"❌ Unexpected error during Git push: {e}")
