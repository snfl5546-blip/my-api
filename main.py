import os

from fastapi import FastAPI, HTTPException, Path
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field
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


# ================= 쇼핑몰: 상품 + 장바구니 =================
# 로그인 없이 "브라우저마다 고유한 cart_id" 로 장바구니를 구분합니다.
CartId = Path(min_length=8, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


class CartItemIn(BaseModel):
    product_id: int
    quantity: int = Field(default=1, ge=1, le=99)


class QuantityIn(BaseModel):
    quantity: int = Field(ge=0, le=99)  # 0 이면 삭제


def read_cart(cart_id: str):
    """장바구니 항목 + 상품 정보를 합쳐서 돌려줍니다."""
    rows = (
        sb.table("cart_items")
        .select("product_id, quantity, products(id, name, price, emoji, category)")
        .eq("cart_id", cart_id)
        .order("created_at")
        .execute()
        .data
    )
    items = []
    for r in rows:
        p = r["products"]
        items.append(
            {
                "product_id": r["product_id"],
                "name": p["name"],
                "emoji": p["emoji"],
                "price": p["price"],
                "quantity": r["quantity"],
                "subtotal": p["price"] * r["quantity"],
            }
        )
    total = sum(i["subtotal"] for i in items)
    count = sum(i["quantity"] for i in items)
    return {"cart_id": cart_id, "items": items, "count": count, "total": total}


@app.get("/products")
def list_products():
    return sb.table("products").select("*").order("id").execute().data


@app.get("/cart/{cart_id}")
def get_cart(cart_id: str = CartId):
    return read_cart(cart_id)


@app.post("/cart/{cart_id}/items")
def add_to_cart(item: CartItemIn, cart_id: str = CartId):
    exists = sb.table("products").select("id").eq("id", item.product_id).execute().data
    if not exists:
        raise HTTPException(status_code=404, detail="product not found")
    cur = (
        sb.table("cart_items")
        .select("id, quantity")
        .eq("cart_id", cart_id)
        .eq("product_id", item.product_id)
        .execute()
        .data
    )
    if cur:
        qty = min(99, cur[0]["quantity"] + item.quantity)
        sb.table("cart_items").update({"quantity": qty}).eq("id", cur[0]["id"]).execute()
    else:
        sb.table("cart_items").insert(
            {"cart_id": cart_id, "product_id": item.product_id, "quantity": item.quantity}
        ).execute()
    return read_cart(cart_id)


@app.patch("/cart/{cart_id}/items/{product_id}")
def set_quantity(product_id: int, body: QuantityIn, cart_id: str = CartId):
    if body.quantity == 0:
        sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
    else:
        sb.table("cart_items").update({"quantity": body.quantity}).eq(
            "cart_id", cart_id
        ).eq("product_id", product_id).execute()
    return read_cart(cart_id)


@app.delete("/cart/{cart_id}/items/{product_id}")
def remove_item(product_id: int, cart_id: str = CartId):
    sb.table("cart_items").delete().eq("cart_id", cart_id).eq("product_id", product_id).execute()
    return read_cart(cart_id)


@app.delete("/cart/{cart_id}")
def clear_cart(cart_id: str = CartId):
    sb.table("cart_items").delete().eq("cart_id", cart_id).execute()
    return read_cart(cart_id)
