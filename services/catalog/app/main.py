from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import or_

from app.db import Base, engine, get_db
from app.models import Product
from app.schemas import ProductCreate, ProductOut


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Dev convenience: auto-create tables. Swap for Alembic migrations later.
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="ScaleCart - Catalog Service", lifespan=lifespan)


@app.get("/health")
def health():
    return {"status": "ok", "service": "catalog"}


@app.get("/products", response_model=list[ProductOut])
def list_products(
    search: str | None = Query(
        None, description="Case-insensitive substring match on name or SKU"
    ),
    skip: int = Query(0, ge=0, description="Number of results to skip"),
    limit: int = Query(20, ge=1, le=100, description="Max results to return"),
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if search:
        like = f"%{search}%"
        query = query.filter(or_(Product.name.ilike(like), Product.sku.ilike(like)))
    return query.order_by(Product.id).offset(skip).limit(limit).all()


@app.get("/products/{product_id}", response_model=ProductOut)
def get_product(product_id: int, db: Session = Depends(get_db)):
    product = db.get(Product, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product


@app.post("/products", response_model=ProductOut, status_code=201)
def create_product(payload: ProductCreate, db: Session = Depends(get_db)):
    existing = db.query(Product).filter(Product.sku == payload.sku).first()
    if existing:
        raise HTTPException(status_code=409, detail="SKU already exists")
    product = Product(**payload.model_dump())
    db.add(product)
    db.commit()
    db.refresh(product)
    return product
