# main.py
import os
from datetime import datetime
from dotenv import load_dotenv
from typing import List, Optional, Dict, Any, Annotated

from fastapi import FastAPI, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse # Importar FileResponse
from pymongo import MongoClient
from pymongo.server_api import ServerApi
from bson import ObjectId
from pydantic import BaseModel, Field, BeforeValidator, ConfigDict

# Load environment variables from .env file
load_dotenv()

# --- MongoDB Connection ---
db_client: MongoClient = None
db: Any = None

def init_connection():
    """Initializes and returns the MongoDB connection."""
    global db_client, db
    try:
        mongo_url = os.getenv("DATABASE_URL")
        if not mongo_url:
            print("DATABASE_URL not found in .env, using default URL. PLEASE SET IT IN RENDER ENVIRONMENT VARIABLES.")
            # Default URL - REPLACE WITH YOUR ACTUAL MONGODB CONNECTION STRING
            # This default URL is for local testing ONLY. It will likely fail on Render.
            mongo_url = "mongodb+srv://user:password@cluster.mongodb.net/?retryWrites=true&w=majority"
        
        db_client = MongoClient(mongo_url, server_api=ServerApi('1'))
        db = db_client["prueba"] # Database name
        
        db_client.admin.command('ping')
        print("✅ MongoDB connection established successfully!")
        return db
    except Exception as e:
        print(f"❌ Error connecting to MongoDB: {e}")
        raise RuntimeError(f"Failed to connect to MongoDB: {e}")

# Initialize connection when the application starts
init_connection()

# Define collections
startups_collection = db["startup"]
session_offers_collection = db["session_offers"]
session_requests_collection = db["session_requests"]
session_history_collection = db["session_history"]

# --- Pydantic Models for Data Validation and Serialization ---

PyObjectId = Annotated[str, BeforeValidator(str)]

def none_to_empty_str(v: Optional[str]) -> str:
    return v if v is not None else ""

class StartupBase(BaseModel):
    company: str
    contact: Optional[str] = None
    email: Optional[str] = None
    sector: Optional[str] = None
    stage: Optional[str] = None
    description: Optional[str] = None
    website: Optional[str] = None
    sessions_allotted_to_receive: int = 2
    sessions_received: int = 0
    sessions_lent: int = 0

class StartupInDB(StartupBase):
    id: PyObjectId = Field(alias="_id", default=None)
    sector: Annotated[str, BeforeValidator(none_to_empty_str)] = Field(None, description="Sector of the startup", validate_default=True)
    stage: Annotated[str, BeforeValidator(none_to_empty_str)] = Field(None, description="Stage of the startup (e.g., Seed, Series A)", validate_default=True)

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True, json_schema_extra={
        "example": {
            "id": "60c72b2f9b1e8b001c8e4d7a",
            "company": "Tech Innovators",
            "contact": "Jane Doe",
            "email": "jane.doe@techinnovators.com",
            "sector": "Software",
            "stage": "Seed",
            "description": "Developing cutting-edge AI solutions.",
            "website": "techinnovators.com",
            "sessions_allotted_to_receive": 2,
            "sessions_received": 0,
            "sessions_lent": 0
        }
    })

class SessionOfferCreate(BaseModel):
    offering_startup_id: PyObjectId
    offering_startup_name: str
    topic: str

class SessionOfferInDB(SessionOfferCreate):
    id: PyObjectId = Field(alias="_id", default=None)
    status: str = "available"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    claimed_by_startup_id: Optional[PyObjectId] = None
    claimed_by_startup_name: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class SessionRequestCreate(BaseModel):
    requesting_startup_id: PyObjectId
    requesting_startup_name: str
    topic: str

class SessionRequestInDB(SessionRequestCreate):
    id: PyObjectId = Field(alias="_id", default=None)
    status: str = "pending"
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    fulfilled_by_offer_id: Optional[PyObjectId] = None
    fulfilled_by_startup_id: Optional[PyObjectId] = None
    fulfilled_by_startup_name: Optional[str] = None
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)

class ClaimSessionRequest(BaseModel):
    claiming_startup_id: PyObjectId
    claiming_startup_name: str

class SessionHistoryInDB(BaseModel):
    id: PyObjectId = Field(alias="_id", default=None)
    type: str = "claimed_session"
    offer_id: PyObjectId
    offering_startup_id: PyObjectId
    offering_startup_name: str
    claiming_startup_id: PyObjectId
    claiming_startup_name: str
    topic: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


# --- FastAPI Application ---
app = FastAPI(
    title="Startup Mentorship Marketplace API",
    description="API for managing startups, mentorship offers, and requests.",
    version="1.0.0",
)

# CORS Middleware to allow requests from your frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Allows all origins for development. Restrict in production!
    allow_credentials=True,
    allow_methods=["*"],  # Allows all methods
    allow_headers=["*"],  # Allows all headers
)

# Montar la carpeta 'static' para servir archivos estáticos (CSS, JS, imágenes, etc.)
# Esto NO servirá index.html por defecto, solo los archivos dentro de 'static'
app.mount("/static", StaticFiles(directory="static"), name="static")

# Endpoint para servir el archivo index.html en la raíz
@app.get("/")
async def serve_frontend():
    """Serves the main frontend application (index.html)."""
    return FileResponse("static/index.html")

@app.get("/api") # Endpoint principal de la API para el dashboard
async def get_dashboard_data():
    """
    Returns a comprehensive overview of all dashboard data, including:
    - Total number of registered startups.
    - Contact information for all startups.
    - All registered startups with their session counts.
    - Available session offers.
    - Pending session requests.
    - Completed session history.
    """
    try:
        print("API endpoint /api was hit!") # Log para depuración
        # Fetch total startups
        total_startups = startups_collection.count_documents({})

        # Fetch startup contacts
        contacts = []
        cursor = startups_collection.find(
            {"contact": {"$ne": None, "$ne": ""}},
            {"company": 1, "contact": 1, "email": 1, "sector": 1, "_id": 0}
        )
        for doc in cursor:
            contacts.append(doc)

        # Fetch all startups (for suggestions and session counts)
        all_startups_data = []
        for doc in startups_collection.find({}):
            # Ensure session fields are initialized if missing
            if 'sessions_allotted_to_receive' not in doc:
                doc['sessions_allotted_to_receive'] = 2
                startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_allotted_to_receive": 2}})
            if 'sessions_received' not in doc:
                doc['sessions_received'] = 0
                startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_received": 0}})
            if 'sessions_lent' not in doc:
                doc['sessions_lent'] = 0
                startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_lent": 0}})
            
            all_startups_data.append(StartupInDB(**doc).model_dump()) 

        # Fetch available session offers
        available_offers = []
        for doc in session_offers_collection.find({"status": "available"}):
            available_offers.append(SessionOfferInDB(**doc).model_dump(by_alias=True))

        # Fetch pending session requests
        pending_requests = []
        for doc in session_requests_collection.find({"status": "pending"}):
            pending_requests.append(SessionRequestInDB(**doc).model_dump(by_alias=True))

        # Fetch session history
        session_history = []
        for doc in session_history_collection.find({}):
            session_history.append(SessionHistoryInDB(**doc).model_dump(by_alias=True))

        return {
            "message": "Dashboard data loaded successfully!",
            "key_statistics": {
                "total_startups": total_startups
            },
            "startup_contacts": contacts,
            "all_startups": all_startups_data,
            "available_session_offers": available_offers,
            "pending_session_requests": pending_requests,
            "session_history": session_history
        }
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error loading dashboard data: {e}")

# --- Startup Endpoints ---
@app.get("/api/startups", response_model=List[StartupInDB])
async def get_all_startups():
    """Retrieve all registered startups."""
    startups = []
    for doc in startups_collection.find({}):
        if 'sessions_allotted_to_receive' not in doc:
            doc['sessions_allotted_to_receive'] = 2
            startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_allotted_to_receive": 2}})
        if 'sessions_received' not in doc:
            doc['sessions_received'] = 0
            startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_received": 0}})
        if 'sessions_lent' not in doc:
            doc['sessions_lent'] = 0
            startups_collection.update_one({"_id": doc['_id']}, {"$set": {"sessions_lent": 0}})
        startups.append(StartupInDB(**doc))
    return startups

@app.get("/api/startups/{startup_id}", response_model=StartupInDB)
async def get_startup_by_id(startup_id: str):
    """Retrieve a specific startup by its ID."""
    try:
        startup_doc = startups_collection.find_one({"_id": ObjectId(startup_id)})
        if startup_doc:
            if 'sessions_allotted_to_receive' not in startup_doc:
                startup_doc['sessions_allotted_to_receive'] = 2
                startups_collection.update_one({"_id": startup_doc['_id']}, {"$set": {"sessions_allotted_to_receive": 2}})
            if 'sessions_received' not in startup_doc:
                startup_doc['sessions_received'] = 0
                startups_collection.update_one({"_id": startup_doc['_id']}, {"$set": {"sessions_received": 0}})
            if 'sessions_lent' not in startup_doc:
                startup_doc['sessions_lent'] = 0
                startups_collection.update_one({"_id": startup_doc['_id']}, {"$set": {"sessions_lent": 0}})
            return StartupInDB(**startup_doc)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Startup not found")
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"Invalid Startup ID or other error: {e}")

@app.get("/api/startups_contacts")
async def get_startups_contacts():
    """Retrieve contact information for all startups."""
    contacts = []
    cursor = startups_collection.find(
        {"contact": {"$ne": None, "$ne": ""}},
        {"company": 1, "contact": 1, "email": 1, "sector": 1, "_id": 0}
    )
    for doc in cursor:
        contacts.append(doc)
    return contacts

@app.get("/api/startups_total")
async def get_total_startups():
    """Get the total count of registered startups."""
    total = startups_collection.count_documents({})
    return {"total_startups": total}

# --- Session Offer Endpoints ---
@app.post("/api/session-offers", response_model=SessionOfferInDB, status_code=status.HTTP_201_CREATED)
async def create_session_offer(offer: SessionOfferCreate):
    """Create a new session offer."""
    try:
        offering_startup_obj_id = ObjectId(offer.offering_startup_id)
        current_startup_data = startups_collection.find_one({"_id": offering_startup_obj_id})

        if not current_startup_data:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Offering startup not found.")

        sessions_allotted = current_startup_data.get('sessions_allotted_to_receive', 0)
        sessions_received = current_startup_data.get('sessions_received', 0)

        if sessions_allotted <= sessions_received:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"{offer.offering_startup_name} does not have an available session slot to lend (they have already received or lent all their initially allotted sessions)."
            )

        new_offer_doc = offer.model_dump()
        new_offer_doc["timestamp"] = datetime.utcnow()
        new_offer_doc["status"] = "available"
        new_offer_doc["claimed_by_startup_id"] = None
        new_offer_doc["claimed_by_startup_name"] = None

        result = session_offers_collection.insert_one(new_offer_doc)
        
        # Update session_lent count for the offering startup
        startups_collection.update_one(
            {"_id": offering_startup_obj_id},
            {"$inc": {"sessions_lent": 1}}
        )
        
        created_offer = session_offers_collection.find_one({"_id": result.inserted_id})
        return SessionOfferInDB(**created_offer)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating session offer: {e}")

@app.get("/api/session-offers", response_model=List[SessionOfferInDB])
async def get_available_session_offers():
    """Retrieve all available session offers."""
    offers = []
    for doc in session_offers_collection.find({"status": "available"}):
        offers.append(SessionOfferInDB(**doc))
    return offers

@app.post("/api/session-offers/{offer_id}/claim", response_model=SessionHistoryInDB)
async def claim_session_offer(offer_id: str, claim_request: ClaimSessionRequest):
    """Claim an available session offer."""
    try:
        offer_obj_id = ObjectId(offer_id)
        claiming_startup_obj_id = ObjectId(claim_request.claiming_startup_id)

        selected_offer_doc = session_offers_collection.find_one({"_id": offer_obj_id, "status": "available"})
        if not selected_offer_doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Session offer not found or not available.")

        # Prevent a startup from claiming its own offer
        if selected_offer_doc['offering_startup_id'] == str(claiming_startup_obj_id):
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot claim a session offered by your own startup.")

        # Update the session offer status
        session_offers_collection.update_one(
            {"_id": offer_obj_id},
            {"$set": {
                "status": "claimed",
                "claimed_by_startup_id": claim_request.claiming_startup_id,
                "claimed_by_startup_name": claim_request.claiming_startup_name
            }}
        )

        # Find and fulfill a matching pending request from the claiming startup, if any
        matching_request = session_requests_collection.find_one({
            "requesting_startup_id": claim_request.claiming_startup_id,
            "topic": selected_offer_doc['topic'],
            "status": "pending"
        })

        if matching_request:
            session_requests_collection.update_one(
                {"_id": matching_request['_id']},
                {"$set": {
                    "status": "fulfilled",
                    "fulfilled_by_offer_id": str(selected_offer_doc['_id']),
                    "fulfilled_by_startup_id": selected_offer_doc['offering_startup_id'],
                    "fulfilled_by_startup_name": selected_offer_doc['offering_startup_name']
                }}
            )
        
        # Update sessions_received count for the claiming startup
        startups_collection.update_one(
            {"_id": claiming_startup_obj_id},
            {"$inc": {"sessions_received": 1}}
        )

        # Record the transaction in session history
        history_entry = {
            "type": "claimed_session",
            "offer_id": str(selected_offer_doc['_id']),
            "offering_startup_id": selected_offer_doc['offering_startup_id'],
            "offering_startup_name": selected_offer_doc['offering_startup_name'],
            "claiming_startup_id": claim_request.claiming_startup_id,
            "claiming_startup_name": claim_request.claiming_startup_name,
            "topic": selected_offer_doc['topic'],
            "timestamp": datetime.utcnow()
        }
        history_result = session_history_collection.insert_one(history_entry)
        
        created_history = session_history_collection.find_one({"_id": history_result.inserted_id})
        return SessionHistoryInDB(**created_history)

    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error claiming session: {e}")

# --- Session Request Endpoints ---
@app.post("/api/session-requests", response_model=SessionRequestInDB, status_code=status.HTTP_201_CREATED)
async def create_session_request(request: SessionRequestCreate):
    """Create a new session request."""
    try:
        requesting_startup_obj_id = ObjectId(request.requesting_startup_id)
        # Verify requesting startup exists
        if not startups_collection.find_one({"_id": requesting_startup_obj_id}):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Requesting startup not found.")

        new_request_doc = request.model_dump()
        new_request_doc["timestamp"] = datetime.utcnow()
        new_request_doc["status"] = "pending"
        new_request_doc["fulfilled_by_offer_id"] = None
        new_request_doc["fulfilled_by_startup_id"] = None
        new_request_doc["fulfilled_by_startup_name"] = None

        result = session_requests_collection.insert_one(new_request_doc)
        created_request = session_requests_collection.find_one({"_id": result.inserted_id})
        return SessionRequestInDB(**created_request)
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=f"Error creating session request: {e}")

@app.get("/api/session-requests", response_model=List[SessionRequestInDB])
async def get_pending_session_requests():
    """Retrieve all pending session requests."""
    requests = []
    for doc in session_requests_collection.find({"status": "pending"}):
        requests.append(SessionRequestInDB(**doc))
    return requests

# --- Session History Endpoints ---
@app.get("/api/session-history", response_model=List[SessionHistoryInDB])
async def get_session_history():
    """Retrieve all completed session transactions."""
    history = []
    for doc in session_history_collection.find({}):
        history.append(SessionHistoryInDB(**doc))
    return history