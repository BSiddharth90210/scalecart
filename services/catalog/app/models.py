from sqlalchemy import Column, Integer, String, Numeric, Text
from app.db import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    sku = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    price_cents = Column(Integer, nullable=False)  # store money as integer cents
    currency = Column(String(3), nullable=False, default="usd")
    stock_qty = Column(Integer, nullable=False, default=0)
