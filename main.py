import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv
from supabase import create_client

load_dotenv()

# 로컬에선 .env를 읽고, Railway에선 Variables가 이미 들어 있음
SUPABASE_URL = os.environ["SUPABASE_URL"]
SUPABASE_SECRET_KEY = os.environ["SUPABASE_SECRET_KEY"]
FRONT_ORIGINS = [
    o.strip() for o in os.getenv("FRONT_ORIGINS", "").split(",") if o.strip()
]

sb = create_client(SUPABASE_URL, SUPABASE_SECRET_KEY)

app = FastAPI(title="my-api")

app.add_middleware(
    CORSMiddleware,
    allow_origins=FRONT_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health():
    return {"status": "ok"}

@app.get("/v")
def health():
    return {"s":100, "t":200}

# ---- Supabase 연동 확인용 엔드포인트 (supabase/schema.sql 의 notes 테이블 사용) ----
class NoteIn(BaseModel):
    content: str


@app.get("/health/db")
def health_db():
    try:
        sb.table("notes").select("id").limit(1).execute()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"DB error: {e}")


@app.get("/notes")
def list_notes():
    res = sb.table("notes").select("*").order("id", desc=True).limit(50).execute()
    return res.data


@app.post("/notes", status_code=201)
def create_note(note: NoteIn):
    content = note.content.strip()
    if not content:
        raise HTTPException(status_code=400, detail="content is empty")
    res = sb.table("notes").insert({"content": content}).execute()
    return res.data[0]
