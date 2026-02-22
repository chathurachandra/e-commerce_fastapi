from sqlalchemy import Column, Integer, String, Float, Text
from app.db.base import Base
class Product(Base):
    __tablename__ = "products"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(255), index=True, nullable=False)
    description = Column(Text)
    category = Column(String(100), index=True)
    price = Column(Float, nullable=False)
    rating = Column(Float, default=0.0)