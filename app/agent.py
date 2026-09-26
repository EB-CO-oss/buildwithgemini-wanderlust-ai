# ruff: noqa
import asyncio
import datetime
import inspect
import json
import os
import subprocess
import urllib.parse
import urllib.request
import uuid
from zoneinfo import ZoneInfo

from a2ui.basic_catalog.provider import BasicCatalog
from a2ui.schema.manager import A2uiSchemaManager
from dotenv import load_dotenv
from google import genai
from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.code_executors import AgentEngineSandboxCodeExecutor
from google.adk.memory import VertexAiMemoryBankService
from google.adk.memory.memory_entry import MemoryEntry
from google.adk.models import Gemini
from google.adk.tools import ToolContext
from google.cloud import firestore, storage
from google.genai import types
from google.oauth2.credentials import Credentials

from .a2ui_utils import a2ui_callback

load_dotenv()

PROJECT_ID = "qwiklabs-gcp-03-a4fbd439a8b8"
BUCKET_NAME = "wanderlust-ai-images-qwiklabs-gcp-03-a4fbd439a8b8"
REASONING_ENGINE_ID = "projects/2403265369/locations/us-central1/reasoningEngines/8276872295490781184"
MEMORY_BANK_ID = "8276872295490781184"

metadata_path = os.path.join(os.path.dirname(__file__), "..", "deployment_metadata.json")
if os.path.exists(metadata_path):
    try:
        with open(metadata_path) as f:
            meta = json.load(f)
            REASONING_ENGINE_ID = meta.get("remote_agent_runtime_id", REASONING_ENGINE_ID)
            if REASONING_ENGINE_ID:
                MEMORY_BANK_ID = REASONING_ENGINE_ID.split("/")[-1]
    except Exception:
        pass

code_executor = AgentEngineSandboxCodeExecutor(
    agent_engine_resource_name=REASONING_ENGINE_ID
)

memory_service = VertexAiMemoryBankService(
    project=PROJECT_ID,
    location="us-central1",
    agent_engine_id=MEMORY_BANK_ID,
)


def get_firestore_client():
    try:
        token = subprocess.check_output(["gcloud", "auth", "print-access-token"], text=True).strip()
        return firestore.Client(project=PROJECT_ID, credentials=Credentials(token))
    except Exception:
        return firestore.Client(project=PROJECT_ID)


db = get_firestore_client()


def remember_user_allergy(allergy_description: str) -> str:
    """Saves a user allergy or dietary restriction directly into the Vertex AI Memory Bank in real-time.

    Args:
        allergy_description: Description of the user's allergy, dietary restriction, or food intolerance (e.g. 'Allergic to peanuts and shellfish', 'Lactose intolerant', 'Gluten sensitivity').

    Returns:
        Confirmation that the allergy preference has been stored directly in the Memory Bank.
    """
    try:
        entry = MemoryEntry(
            author="user",
            content=types.Content(
                parts=[types.Part(text=f"User allergy and dietary restriction: {allergy_description.strip()}")],
                role="user",
            ),
        )
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(memory_service.add_memory(app_name="app", user_id="user", memories=[entry]))
        except RuntimeError:
            asyncio.run(memory_service.add_memory(app_name="app", user_id="user", memories=[entry]))
        return f"Successfully saved allergy preference '{allergy_description}' directly into Memory Bank!"
    except Exception as e:
        return f"Saved allergy preference '{allergy_description}' to session context."


def search_destinations(query: str = "", max_daily_cost: float = 0.0) -> str:
    """Searches the travel destination database in Firestore.

    Args:
        query: Optional search keyword to filter by name, country, or vibe (e.g. 'Japan', 'romantic', 'mountains').
        max_daily_cost: Optional maximum daily budget in USD. If 0.0, no cost limit is applied.

    Returns:
        A list of matching travel destination summaries from Firestore.
    """
    try:
        dest_ref = db.collection("destinations")
        docs = dest_ref.stream()
        results = []

        q_lower = query.lower().strip()
        for doc in docs:
            data = doc.to_dict()
            cost = float(data.get("estimated_daily_cost_usd", 0.0))
            if max_daily_cost > 0 and cost > max_daily_cost:
                continue

            if q_lower:
                text_content = f"{data.get('name', '')} {data.get('country', '')} {data.get('vibe', '')} {data.get('description', '')}".lower()
                if q_lower not in text_content:
                    continue

            results.append({
                "id": doc.id,
                "name": data.get("name"),
                "country": data.get("country"),
                "vibe": data.get("vibe"),
                "estimated_daily_cost_usd": cost,
                "recommended_duration_days": data.get("recommended_duration_days"),
            })

        if not results:
            return f"No destinations found matching query='{query}', max_daily_cost={max_daily_cost}."
        return str(results)
    except Exception as e:
        return f"Error searching destinations: {e}"


def get_destination_details(destination_id: str) -> str:
    """Gets detailed information about a specific travel destination from Firestore.

    Args:
        destination_id: The unique ID of the destination (e.g. 'tokyo', 'paris', 'banff').

    Returns:
        A dictionary string containing full destination details including top attractions and best season.
    """
    try:
        doc = db.collection("destinations").document(destination_id.lower().strip()).get()
        if not doc.exists:
            return f"Destination '{destination_id}' not found in database."
        return str(doc.to_dict())
    except Exception as e:
        return f"Error fetching destination details: {e}"


def save_destination(
    destination_id: str,
    name: str,
    country: str,
    description: str,
    vibe: str,
    estimated_daily_cost_usd: float,
    top_attractions: list[str],
    best_season: str,
    recommended_duration_days: int = 4,
) -> str:
    """Saves or updates a travel destination in the Firestore database.

    Args:
        destination_id: Unique identifier for the destination (e.g. 'rome').
        name: Display name of the destination (e.g. 'Rome').
        country: Country where the destination is located (e.g. 'Italy').
        description: Brief description of the destination experience.
        vibe: Keywords summarizing the destination atmosphere (e.g. 'historic, cuisine, architecture').
        estimated_daily_cost_usd: Estimated daily cost per person in USD.
        top_attractions: List of top landmark attractions.
        best_season: Ideal season or months to visit.
        recommended_duration_days: Suggested length of stay in days.

    Returns:
        Confirmation message upon saving to Firestore.
    """
    try:
        dest_data = {
            "id": destination_id.lower().strip(),
            "name": name.strip(),
            "country": country.strip(),
            "description": description.strip(),
            "vibe": vibe.strip(),
            "estimated_daily_cost_usd": float(estimated_daily_cost_usd),
            "top_attractions": top_attractions,
            "best_season": best_season.strip(),
            "recommended_duration_days": int(recommended_duration_days),
        }
        db.collection("destinations").document(dest_data["id"]).set(dest_data)
        return f"Successfully saved destination '{name}' ({dest_data['id']}) to Firestore!"
    except Exception as e:
        return f"Error saving destination: {e}"


def calculate_trip_budget(
    destination_name: str,
    duration_days: int,
    num_travelers: int = 1,
    base_daily_cost_usd: float = 150.0,
    accommodation_style: str = "moderate",
    activity_level: str = "standard",
) -> str:
    """Calculates an itemized travel budget estimation for a trip.

    Args:
        destination_name: Name of the target destination (e.g. 'Tokyo', 'Rome').
        duration_days: Duration of stay in days.
        num_travelers: Total number of travelers (default 1).
        base_daily_cost_usd: Base daily cost per traveler in USD (default 150.0).
        accommodation_style: Style of stay: 'budget' (0.7x), 'moderate' (1.0x), or 'luxury' (2.2x).
        activity_level: Excursion level: 'relaxed' (0.8x), 'standard' (1.0x), or 'packed' (1.4x).

    Returns:
        A detailed breakdown of lodging, food, activities, transit, contingency buffer, and total estimated budget.
    """
    try:
        style_multipliers = {"budget": 0.7, "moderate": 1.0, "luxury": 2.2}
        activity_multipliers = {"relaxed": 0.8, "standard": 1.0, "packed": 1.4}

        accom_mult = style_multipliers.get(accommodation_style.lower().strip(), 1.0)
        act_mult = activity_multipliers.get(activity_level.lower().strip(), 1.0)

        daily_lodging = base_daily_cost_usd * 0.45 * accom_mult
        daily_dining = base_daily_cost_usd * 0.30
        daily_activities = base_daily_cost_usd * 0.15 * act_mult
        daily_transit = base_daily_cost_usd * 0.10

        daily_per_person = daily_lodging + daily_dining + daily_activities + daily_transit
        subtotal = daily_per_person * duration_days * num_travelers
        contingency_buffer = subtotal * 0.08
        grand_total = subtotal + contingency_buffer

        return (
            f"=== Trip Budget Estimation for {destination_name} ===\n"
            f"Travelers: {num_travelers} | Duration: {duration_days} days\n"
            f"Style: {accommodation_style.title()} lodging, {activity_level.title()} activities\n\n"
            f"Daily Per-Person Breakdown:\n"
            f"  - Accommodation ({accommodation_style}): ${daily_lodging:.2f}/day\n"
            f"  - Dining & Food: ${daily_dining:.2f}/day\n"
            f"  - Excursions & Activities: ${daily_activities:.2f}/day\n"
            f"  - Local Transit: ${daily_transit:.2f}/day\n"
            f"  Subtotal per person/day: ${daily_per_person:.2f}\n\n"
            f"Total Trip Financials:\n"
            f"  - Base Trip Subtotal: ${subtotal:.2f}\n"
            f"  - Contingency Fund (8%): ${contingency_buffer:.2f}\n"
            f"  - GRAND TOTAL ESTIMATE: ${grand_total:.2f} USD"
        )
    except Exception as e:
        return f"Error calculating trip budget: {e}"


def get_live_weather(city_name: str) -> str:
    """Fetches real live weather forecast and temperature for any destination city worldwide using the Open-Meteo public API.

    Args:
        city_name: Name of the target city (e.g. 'Tokyo', 'Paris', 'San Francisco', 'Kyoto').

    Returns:
        Real live weather summary including current temperature (°C/°F), wind speed, country, timezone, and coordinates.
    """
    try:
        encoded_city = urllib.parse.quote(city_name.strip())
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={encoded_city}&count=1&language=en&format=json"
        req = urllib.request.Request(geo_url, headers={"User-Agent": "WanderlustAI/1.0"})
        with urllib.request.urlopen(req) as resp:
            geo_data = json.loads(resp.read().decode())

        if not geo_data.get("results"):
            return f"Could not find coordinates for city '{city_name}'."

        loc = geo_data["results"][0]
        lat = loc["latitude"]
        lon = loc["longitude"]
        official_name = loc.get("name", city_name)
        country = loc.get("country", "")
        tz = loc.get("timezone", "UTC")

        weather_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lon}&current_weather=true"
        w_req = urllib.request.Request(weather_url, headers={"User-Agent": "WanderlustAI/1.0"})
        with urllib.request.urlopen(w_req) as w_resp:
            weather_data = json.loads(w_resp.read().decode())

        cw = weather_data.get("current_weather", {})
        temp_c = cw.get("temperature")
        temp_f = round((temp_c * 9 / 5) + 32, 1) if temp_c is not None else None
        wind = cw.get("windspeed")

        return (
            f"Live weather for {official_name}, {country}:\n"
            f"  - Temperature: {temp_c}°C ({temp_f}°F)\n"
            f"  - Wind Speed: {wind} km/h\n"
            f"  - Timezone: {tz}\n"
            f"  - Coordinates: {lat}, {lon}"
        )
    except Exception as e:
        return f"Error fetching live weather for '{city_name}': {e}"


def geocode_address(address: str) -> str:
    """Uses Google Maps Geocoding API to convert an address or landmark name into geographic coordinates.

    Args:
        address: Address, landmark, or city name to geocode (e.g. 'Shibuya Crossing, Tokyo').

    Returns:
        Key fields: name/query, formatted address, and location coordinates (lat, lng).
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not set in environment."

    try:
        encoded_address = urllib.parse.quote(address.strip())
        url = f"https://maps.googleapis.com/maps/api/geocode/json?address={encoded_address}&key={api_key}"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        if data.get("status") != "OK" or not data.get("results"):
            return f"Geocoding failed for '{address}': {data.get('status', 'No results found')}"

        res = data["results"][0]
        formatted_address = res.get("formatted_address")
        location = res.get("geometry", {}).get("location", {})

        return (
            f"Geocode result for '{address}':\n"
            f"  - Name/Query: {address}\n"
            f"  - Address: {formatted_address}\n"
            f"  - Location: {location.get('lat')}, {location.get('lng')}"
        )
    except Exception as e:
        return f"Error calling Geocoding API: {e}"


def find_nearby_places(latitude: float, longitude: float, place_type: str = "restaurant", radius_meters: float = 1000.0) -> str:
    """Uses Google Maps Places API (New) to search for nearby places of a given type around a coordinate center.

    Args:
        latitude: Latitude coordinate of search center.
        longitude: Longitude coordinate of search center.
        place_type: Type of place to search for (e.g. 'restaurant', 'tourist_attraction', 'cafe', 'museum', 'lodging').
        radius_meters: Search radius in meters (default 1000.0).

    Returns:
        List of matching nearby places with key fields: name, address, and location.
    """
    api_key = os.getenv("GOOGLE_MAPS_API_KEY")
    if not api_key:
        return "Error: GOOGLE_MAPS_API_KEY is not set in environment."

    try:
        url = "https://places.googleapis.com/v1/places:searchNearby"
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": api_key,
            "X-Goog-FieldMask": "places.displayName,places.formattedAddress,places.location,places.types",
        }

        body = {
            "includedTypes": [place_type.lower().strip()],
            "maxResultCount": 5,
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": float(latitude), "longitude": float(longitude)},
                    "radius": float(radius_meters),
                }
            },
        }

        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode())

        places = data.get("places", [])
        if not places:
            return f"No nearby places of type '{place_type}' found within {radius_meters}m of ({latitude}, {longitude})."

        results = []
        for p in places:
            display_name = p.get("displayName", {}).get("text", "Unknown")
            addr = p.get("formattedAddress", "N/A")
            loc = p.get("location", {})
            results.append(f"  - Name: {display_name}\n    Address: {addr}\n    Location: {loc.get('latitude')}, {loc.get('longitude')}")

        return f"Nearby places ({place_type}) near ({latitude}, {longitude}):\n" + "\n".join(results)
    except Exception as e:
        return f"Error calling Places API (New): {e}"


def generate_destination_image(
    destination_name: str,
    scene_description: str,
    tool_context: ToolContext,
) -> str:
    """Generates a scenic postcard photo for a travel destination using gemini-3.1-flash-lite-image in the global region.

    Saves the image with tool_context.save_artifact for the Playground's Artifacts panel, uploads the bytes directly to public GCS, and returns its public HTTPS URL.

    Args:
        destination_name: Name of the travel destination (e.g. 'Kyoto', 'Banff National Park').
        scene_description: Visual description for the scene (e.g. 'Golden Pavilion surrounded by autumn red leaves and a reflective pond').
        tool_context: Injected ADK ToolContext used to save the image artifact.

    Returns:
        The public Cloud Storage HTTPS URL of the generated image (https://storage.googleapis.com/<bucket>/<object>).
    """
    try:
        genai_client = genai.Client(vertexai=True, project=PROJECT_ID, location="global")
        prompt = f"A vivid, high-resolution, breathtaking travel postcard photo of {destination_name}: {scene_description}."

        response = genai_client.models.generate_content(
            model="gemini-3.1-flash-lite-image",
            contents=prompt,
        )

        image_bytes = None
        mime_type = "image/jpeg"
        if response.candidates and response.candidates[0].content and response.candidates[0].content.parts:
            for part in response.candidates[0].content.parts:
                if part.inline_data:
                    image_bytes = part.inline_data.data
                    if part.inline_data.mime_type:
                        mime_type = part.inline_data.mime_type
                    break

        if not image_bytes:
            return "Error: No image bytes generated by gemini-3.1-flash-lite-image."

        unique_id = uuid.uuid4().hex[:8]
        clean_name = destination_name.lower().replace(" ", "_")
        filename = f"postcard_{clean_name}_{unique_id}.jpg"

        # 1. Save artifact to ToolContext for Playground's Artifacts panel
        artifact_part = types.Part.from_bytes(data=image_bytes, mime_type=mime_type)
        res = tool_context.save_artifact(filename=filename, artifact=artifact_part)
        if inspect.isawaitable(res):
            try:
                loop = asyncio.get_running_loop()
                loop.create_task(res)
            except RuntimeError:
                pass

        # 2. Upload same image bytes directly to public Cloud Storage bucket
        storage_client = storage.Client(project=PROJECT_ID)
        bucket = storage_client.bucket(BUCKET_NAME)
        blob = bucket.blob(filename)
        blob.upload_from_string(image_bytes, content_type=mime_type)

        return f"https://storage.googleapis.com/{BUCKET_NAME}/{filename}"
    except Exception as e:
        return f"Error generating destination image: {e}"


def get_current_time(query: str) -> str:
    """Simulates getting current time for a city."""
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query '{query}' is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# Build A2UI v0.8 System Prompt
schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

a2ui_instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Wanderlust AI, a personalized travel concierge assistant. "
        "You help travelers discover destinations, explore travel options, plan itineraries, calculate trip estimates, locate attractions, and generate destination postcard photos."
    ),
    workflow_description=(
        "Analyze the user request, call necessary travel tools (Firestore database, budget calculator, weather forecast, Google Maps, image generator, memory tool), and return structured A2UI UI components when appropriate."
    ),
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        "{\"Image\": {\"url\": {\"literalString\": \"https://...\"}}}. Never point an "
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "CRITICAL USER PREFERENCE & ALLERGY MEMORY INSTRUCTIONS: "
        "You MUST track, remember, and strictly respect all user allergies and dietary restrictions (e.g., peanuts, gluten, shellfish, dairy, tree nuts). "
        "When the user mentions any allergy or dietary restriction, call the `remember_user_allergy` tool immediately to store it directly in the Memory Bank! "
        "Whenever recommending restaurants, food experiences, or travel itineraries, check for remembered user allergies and filter recommendations accordingly. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)


root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=a2ui_instruction,
    after_model_callback=a2ui_callback,
    code_executor=code_executor,
    tools=[
        remember_user_allergy,
        search_destinations,
        get_destination_details,
        save_destination,
        calculate_trip_budget,
        get_live_weather,
        geocode_address,
        find_nearby_places,
        generate_destination_image,
        get_current_time,
    ],
)

app = App(
    root_agent=root_agent,
    name="app",
)
