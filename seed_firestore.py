import subprocess
from google.cloud import firestore
from google.oauth2.credentials import Credentials

PROJECT_ID = "qwiklabs-gcp-03-a4fbd439a8b8"


def get_firestore_client():
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        return firestore.Client(project=PROJECT_ID, credentials=Credentials(token))
    except Exception:
        return firestore.Client(project=PROJECT_ID)


db = get_firestore_client()

DESTINATIONS = [
    {
        "id": "tokyo",
        "name": "Tokyo",
        "country": "Japan",
        "description": "A bustling metropolis where ultra-modern technology meets ancient traditions, shrines, and world-class cuisine.",
        "vibe": "futuristic, culture, food, shopping",
        "estimated_daily_cost_usd": 180.0,
        "recommended_duration_days": 5,
        "top_attractions": ["Shibuya Crossing", "Senso-ji Temple", "Akihabara", "Meiji Shrine"],
        "best_season": "Spring (Cherry Blossom) / Autumn",
    },
    {
        "id": "kyoto",
        "name": "Kyoto",
        "country": "Japan",
        "description": "The cultural heart of Japan, famous for classical Buddhist temples, gardens, imperial palaces, and wooden houses.",
        "vibe": "serene, historic, nature, traditional",
        "estimated_daily_cost_usd": 150.0,
        "recommended_duration_days": 4,
        "top_attractions": ["Fushimi Inari Shrine", "Kinkaku-ji (Golden Pavilion)", "Arashiyama Bamboo Grove"],
        "best_season": "Spring / Autumn",
    },
    {
        "id": "paris",
        "name": "Paris",
        "country": "France",
        "description": "The City of Light, world-renowned for art, gastronomy, fashion, romantic architecture, and iconic landmarks.",
        "vibe": "romantic, art, fashion, gourmet",
        "estimated_daily_cost_usd": 220.0,
        "recommended_duration_days": 5,
        "top_attractions": ["Eiffel Tower", "Louvre Museum", "Notre-Dame Cathedral", "Montmartre"],
        "best_season": "Late Spring / Early Autumn",
    },
    {
        "id": "banff",
        "name": "Banff National Park",
        "country": "Canada",
        "description": "A breathtaking alpine sanctuary in the Canadian Rockies featuring turquoise glacial lakes and rugged peaks.",
        "vibe": "adventure, mountains, nature, hiking",
        "estimated_daily_cost_usd": 160.0,
        "recommended_duration_days": 4,
        "top_attractions": ["Lake Louise", "Moraine Lake", "Banff Gondola", "Johnston Canyon"],
        "best_season": "Summer (Hiking) / Winter (Skiing)",
    },
    {
        "id": "amalfi-coast",
        "name": "Amalfi Coast",
        "country": "Italy",
        "description": "Dramatic cliffside villages, lemon groves, turquoise Mediterranean waters, and scenic coastal drives.",
        "vibe": "scenic, luxury, ocean, relaxation",
        "estimated_daily_cost_usd": 250.0,
        "recommended_duration_days": 4,
        "top_attractions": ["Positano", "Ravello", "Path of the Gods", "Capri Boat Tour"],
        "best_season": "May - September",
    },
]


def seed():
    print(f"Seeding Firestore in project '{PROJECT_ID}'...")
    collection_ref = db.collection("destinations")
    for dest in DESTINATIONS:
        doc_id = dest["id"]
        collection_ref.document(doc_id).set(dest)
        print(f"  ✓ Seeded destination: {dest['name']} ({doc_id})")
    print("Done seeding Firestore!")


if __name__ == "__main__":
    seed()
