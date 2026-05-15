"""
CausalFunnel - User Analytics Backend
Flask + MongoDB
"""

from flask import Flask, request, jsonify
from flask_cors import CORS
from pymongo import MongoClient, DESCENDING
from bson import ObjectId
from datetime import datetime, timezone
import os
import json

app = Flask(__name__)
CORS(app, supports_credentials=True)

# MongoDB connection
MONGO_URI = os.environ.get("MONGO_URI", "mongodb+srv://maheshgudivada55_db_user:tUkEowpuMnXMxtrZ@cluster0.bodppfz.mongodb.net/?appName=Cluster0")
client = MongoClient(MONGO_URI)
db = client["analytics_db"]
events_collection = db["events"]
sessions_collection = db["sessions"]

# Create indexes for performance
try:
    events_collection.create_index([("session_id", 1), ("timestamp", 1)])
    events_collection.create_index([("event_type", 1)])
    events_collection.create_index([("page_url", 1)])
    sessions_collection.create_index([("session_id", 1)], unique=True)
except Exception as e:
    print(f"Warning: Failed to create indexes: {e}")
    # Continue without indexes


def serialize_doc(doc):
    """Convert MongoDB document to JSON-serializable dict."""
    if doc is None:
        return None
    doc["_id"] = str(doc["_id"])
    return doc


# ─── API: Receive and store events ──────────────────────────────────────────

@app.route("/api/events", methods=["POST"])
def track_event():
    """Receive and store a single event or batch of events."""
    data = request.get_json()

    if not data:
        return jsonify({"error": "No data provided"}), 400

    # Support both single event and batch
    events = data if isinstance(data, list) else [data]
    stored = []

    for event in events:
        # Validate required fields
        required = ["session_id", "event_type", "page_url"]
        missing = [f for f in required if f not in event]
        if missing:
            continue

        event_doc = {
            "session_id": event["session_id"],
            "event_type": event["event_type"],
            "page_url": event["page_url"],
            "timestamp": event.get("timestamp", datetime.now(timezone.utc).isoformat()),
            "metadata": {}
        }

        # Add click coordinates if present
        if event["event_type"] == "click":
            event_doc["metadata"]["x"] = event.get("x", 0)
            event_doc["metadata"]["y"] = event.get("y", 0)
            event_doc["metadata"]["element_tag"] = event.get("element_tag", "")
            event_doc["metadata"]["element_text"] = event.get("element_text", "")[:100]
            event_doc["metadata"]["viewport_width"] = event.get("viewport_width", 0)
            event_doc["metadata"]["viewport_height"] = event.get("viewport_height", 0)

        # Additional metadata for page_view
        if event["event_type"] == "page_view":
            event_doc["metadata"]["referrer"] = event.get("referrer", "")
            event_doc["metadata"]["user_agent"] = event.get("user_agent", "")
            event_doc["metadata"]["screen_width"] = event.get("screen_width", 0)
            event_doc["metadata"]["screen_height"] = event.get("screen_height", 0)

        # Store event
        result = events_collection.insert_one(event_doc)
        event_doc["_id"] = str(result.inserted_id)
        stored.append(event_doc)

        # Upsert session record
        sessions_collection.update_one(
            {"session_id": event["session_id"]},
            {
                "$set": {
                    "last_seen": event_doc["timestamp"],
                    "last_page": event_doc["page_url"]
                },
                "$setOnInsert": {
                    "session_id": event["session_id"],
                    "first_seen": event_doc["timestamp"],
                    "user_agent": event.get("user_agent", ""),
                },
                "$inc": {
                    "total_events": 1,
                    f"event_counts.{event['event_type']}": 1
                },
                "$addToSet": {
                    "pages_visited": event["page_url"]
                }
            },
            upsert=True
        )

    return jsonify({
        "status": "ok",
        "stored": len(stored)
    }), 201


# ─── API: Fetch sessions list ───────────────────────────────────────────────

@app.route("/api/sessions", methods=["GET"])
def get_sessions():
    """Fetch all sessions with event counts, supports pagination & search."""
    page = int(request.args.get("page", 1))
    limit = int(request.args.get("limit", 20))
    search = request.args.get("search", "")
    sort_by = request.args.get("sort", "last_seen")
    order = int(request.args.get("order", -1))

    query = {}
    if search:
        query["session_id"] = {"$regex": search, "$options": "i"}

    skip = (page - 1) * limit
    total = sessions_collection.count_documents(query)

    sessions = list(
        sessions_collection.find(query)
        .sort(sort_by, order)
        .skip(skip)
        .limit(limit)
    )

    return jsonify({
        "sessions": [serialize_doc(s) for s in sessions],
        "total": total,
        "page": page,
        "pages": (total + limit - 1) // limit
    })


# ─── API: Fetch events for a session ────────────────────────────────────────

@app.route("/api/sessions/<session_id>/events", methods=["GET"])
def get_session_events(session_id):
    """Fetch all events for a specific session, ordered by timestamp."""
    events = list(
        events_collection.find({"session_id": session_id})
        .sort("timestamp", 1)
    )

    # Get session summary
    session = sessions_collection.find_one({"session_id": session_id})

    return jsonify({
        "session": serialize_doc(session),
        "events": [serialize_doc(e) for e in events],
        "total": len(events)
    })


# ─── API: Fetch click heatmap data ──────────────────────────────────────────

@app.route("/api/heatmap", methods=["GET"])
def get_heatmap_data():
    """Fetch click data for a specific page URL for heatmap rendering."""
    page_url = request.args.get("page_url", "")

    if not page_url:
        # Return list of unique page URLs that have click events
        pages = events_collection.distinct(
            "page_url",
            {"event_type": "click"}
        )
        return jsonify({"pages": pages})

    clicks = list(
        events_collection.find(
            {"event_type": "click", "page_url": page_url},
            {
                "metadata.x": 1,
                "metadata.y": 1,
                "metadata.element_tag": 1,
                "metadata.element_text": 1,
                "metadata.viewport_width": 1,
                "metadata.viewport_height": 1,
                "timestamp": 1,
                "session_id": 1
            }
        )
    )

    return jsonify({
        "page_url": page_url,
        "clicks": [serialize_doc(c) for c in clicks],
        "total_clicks": len(clicks)
    })


# ─── API: Analytics summary ─────────────────────────────────────────────────

@app.route("/api/analytics/summary", methods=["GET"])
def get_summary():
    """Get overall analytics summary for dashboard."""
    total_sessions = sessions_collection.count_documents({})
    total_events = events_collection.count_documents({})
    total_clicks = events_collection.count_documents({"event_type": "click"})
    total_pageviews = events_collection.count_documents({"event_type": "page_view"})

    # Unique pages
    unique_pages = len(events_collection.distinct("page_url"))

    # Recent activity - events per hour for last 24 hours
    pipeline = [
        {
            "$group": {
                "_id": {
                    "$substr": ["$timestamp", 0, 13]
                },
                "count": {"$sum": 1}
            }
        },
        {"$sort": {"_id": -1}},
        {"$limit": 24}
    ]
    hourly = list(events_collection.aggregate(pipeline))

    # Top pages by events
    top_pages_pipeline = [
        {
            "$group": {
                "_id": "$page_url",
                "events": {"$sum": 1},
                "clicks": {
                    "$sum": {"$cond": [{"$eq": ["$event_type", "click"]}, 1, 0]}
                },
                "views": {
                    "$sum": {"$cond": [{"$eq": ["$event_type", "page_view"]}, 1, 0]}
                }
            }
        },
        {"$sort": {"events": -1}},
        {"$limit": 10}
    ]
    top_pages = list(events_collection.aggregate(top_pages_pipeline))

    return jsonify({
        "total_sessions": total_sessions,
        "total_events": total_events,
        "total_clicks": total_clicks,
        "total_pageviews": total_pageviews,
        "unique_pages": unique_pages,
        "hourly_activity": hourly,
        "top_pages": top_pages
    })


# ─── API: Delete session ────────────────────────────────────────────────────

@app.route("/api/sessions/<session_id>", methods=["DELETE"])
def delete_session(session_id):
    """Delete a session and all its events."""
    events_collection.delete_many({"session_id": session_id})
    sessions_collection.delete_one({"session_id": session_id})
    return jsonify({"status": "deleted", "session_id": session_id})


# ─── API: Get unique page URLs ──────────────────────────────────────────────

@app.route("/api/pages", methods=["GET"])
def get_pages():
    """Get all unique page URLs."""
    pages = events_collection.distinct("page_url")
    return jsonify({"pages": pages})


# ─── Health check ────────────────────────────────────────────────────────────

@app.route("/api/health", methods=["GET"])
def health():
    try:
        client.admin.command("ping")
        return jsonify({"status": "healthy", "database": "connected"})
    except Exception as e:
        return jsonify({"status": "unhealthy", "error": str(e)}), 500


if __name__ == "__main__":
    print("🚀 Analytics API running on http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
