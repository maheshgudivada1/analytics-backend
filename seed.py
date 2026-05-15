"""
Seed script - Populate MongoDB with realistic demo analytics data.
Run: python seed.py
"""

from pymongo import MongoClient
from datetime import datetime, timedelta, timezone
import random
import uuid
import os

MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://maheshgudivada55_db_user:tUkEowpuMnXMxtrZ@cluster0.bodppfz.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client["analytics_db"]

# Clear existing data
db["events"].drop()
db["sessions"].drop()

pages = [
    "https://shop.example.com/",
    "https://shop.example.com/products",
    "https://shop.example.com/products/wireless-headphones",
    "https://shop.example.com/products/smart-watch",
    "https://shop.example.com/products/laptop-stand",
    "https://shop.example.com/cart",
    "https://shop.example.com/checkout",
    "https://shop.example.com/about",
    "https://shop.example.com/contact",
    "https://shop.example.com/blog/tech-trends-2026",
]

user_agents = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/125.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_5) AppleWebKit/605.1.15 Safari/17.5",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0) AppleWebKit/605.1.15 Mobile/15E148",
    "Mozilla/5.0 (Linux; Android 15) AppleWebKit/537.36 Chrome/125.0 Mobile",
    "Mozilla/5.0 (iPad; CPU OS 18_0) AppleWebKit/605.1.15 Mobile/15E148",
]

element_targets = [
    ("button", "Add to Cart"),
    ("a", "View Details"),
    ("button", "Buy Now"),
    ("a", "Home"),
    ("a", "Products"),
    ("button", "Subscribe"),
    ("a", "Learn More"),
    ("img", ""),
    ("div", ""),
    ("nav", ""),
    ("button", "Checkout"),
    ("a", "Sign In"),
    ("input", ""),
    ("button", "Apply Coupon"),
]

NUM_SESSIONS = 45
now = datetime.now(timezone.utc)

events_to_insert = []
sessions_to_insert = []

for i in range(NUM_SESSIONS):
    session_id = f"sess_{uuid.uuid4().hex[:12]}"
    ua = random.choice(user_agents)
    start_time = now - timedelta(
        hours=random.randint(0, 72),
        minutes=random.randint(0, 59)
    )

    # Each session visits 2-8 pages
    num_pages = random.randint(2, 8)
    session_pages = random.choices(pages, k=num_pages)
    current_time = start_time

    event_counts = {"page_view": 0, "click": 0}
    total = 0
    all_pages = set()

    for page in session_pages:
        # Page view event
        event_counts["page_view"] += 1
        total += 1
        all_pages.add(page)

        events_to_insert.append({
            "session_id": session_id,
            "event_type": "page_view",
            "page_url": page,
            "timestamp": current_time.isoformat(),
            "metadata": {
                "referrer": random.choice(["https://google.com", "https://twitter.com", "", "direct"]),
                "user_agent": ua,
                "screen_width": random.choice([1920, 1440, 1366, 375, 414, 768]),
                "screen_height": random.choice([1080, 900, 768, 812, 896, 1024]),
            }
        })

        current_time += timedelta(seconds=random.randint(3, 30))

        # 1-5 clicks per page
        num_clicks = random.randint(1, 5)
        vw = random.choice([1920, 1440, 1366, 375, 414, 768])
        vh = random.choice([1080, 900, 768, 812, 896, 1024])

        for _ in range(num_clicks):
            tag, text = random.choice(element_targets)
            event_counts["click"] += 1
            total += 1

            events_to_insert.append({
                "session_id": session_id,
                "event_type": "click",
                "page_url": page,
                "timestamp": current_time.isoformat(),
                "metadata": {
                    "x": random.randint(20, vw - 20),
                    "y": random.randint(20, min(vh * 3, 3000)),
                    "element_tag": tag,
                    "element_text": text,
                    "viewport_width": vw,
                    "viewport_height": vh,
                }
            })
            current_time += timedelta(seconds=random.randint(1, 15))

        current_time += timedelta(seconds=random.randint(5, 60))

    sessions_to_insert.append({
        "session_id": session_id,
        "first_seen": start_time.isoformat(),
        "last_seen": current_time.isoformat(),
        "last_page": session_pages[-1],
        "user_agent": ua,
        "total_events": total,
        "event_counts": event_counts,
        "pages_visited": list(all_pages),
    })

# Bulk insert
db["events"].insert_many(events_to_insert)
db["sessions"].insert_many(sessions_to_insert)

# Create indexes
db["events"].create_index([("session_id", 1), ("timestamp", 1)])
db["events"].create_index([("event_type", 1)])
db["events"].create_index([("page_url", 1)])
db["sessions"].create_index([("session_id", 1)], unique=True)

print(f"✅ Seeded {len(sessions_to_insert)} sessions with {len(events_to_insert)} events")
