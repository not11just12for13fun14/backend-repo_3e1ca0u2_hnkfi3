import os
from typing import Optional
from fastapi import FastAPI, HTTPException, UploadFile, File
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Document

app = FastAPI(title="Docs Hub API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Utilities

def slugify(text: str) -> str:
    import re
    text = text.lower().strip()
    text = re.sub(r"[^a-z0-9\s-]", "", text)
    text = re.sub(r"[\s-]+", "-", text)
    return text.strip("-")

# Models for responses
class SearchQuery(BaseModel):
    q: str
    category: Optional[str] = None

@app.get("/")
async def root():
    return {"message": "Docs Hub Backend is running"}

@app.get("/test")
def test_database():
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"

            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    import os as _os
    response["database_url"] = "✅ Set" if _os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if _os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response

# Documents CRUD

@app.post("/api/docs")
async def create_doc(payload: Document):
    collection = "document"
    # Ensure slug
    data = payload.model_dump()
    data["slug"] = data.get("slug") or slugify(payload.title)

    # Uniqueness on slug
    existing = db[collection].find_one({"slug": data["slug"]}) if db else None
    if existing:
        raise HTTPException(status_code=400, detail="A document with this slug already exists")

    doc_id = create_document(collection, data)
    return {"id": doc_id, "slug": data["slug"]}

@app.get("/api/docs")
async def list_docs(category: Optional[str] = None, tag: Optional[str] = None, q: Optional[str] = None, limit: int = 50):
    collection = "document"
    filter_q = {}
    if category:
        filter_q["category"] = category
    if tag:
        filter_q["tags"] = {"$in": [tag]}
    if q:
        # basic regex search on title and content
        filter_q["$or"] = [
            {"title": {"$regex": q, "$options": "i"}},
            {"content": {"$regex": q, "$options": "i"}},
            {"tags": {"$regex": q, "$options": "i"}},
        ]
    docs = get_documents(collection, filter_q, limit)
    # map id to string and omit heavy fields for listing
    simplified = [
        {
            "id": str(d.get("_id")),
            "title": d.get("title"),
            "slug": d.get("slug"),
            "category": d.get("category"),
            "tags": d.get("tags", []),
            "cover_image": d.get("cover_image") if d.get("cover_image") else None,
        }
        for d in docs
    ]
    return simplified

@app.get("/api/docs/{slug}")
async def get_doc(slug: str):
    d = db["document"].find_one({"slug": slug})
    if not d:
        raise HTTPException(status_code=404, detail="Document not found")
    d["id"] = str(d.pop("_id"))
    return d

@app.delete("/api/docs/{slug}")
async def delete_doc(slug: str):
    result = db["document"].delete_one({"slug": slug})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Document not found")
    return {"ok": True}

# Simple image upload to base64 (for convenience in this sandbox)
@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    import base64
    content = await file.read()
    b64 = base64.b64encode(content).decode("utf-8")
    data_url = f"data:{file.content_type};base64,{b64}"
    return {"data_url": data_url, "mime": file.content_type}
