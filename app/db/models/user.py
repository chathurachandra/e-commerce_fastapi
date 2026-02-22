from sqlalchemy import Column, Integer, String
from app.db.base import Base
class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    email = Column(String(255), unique=True, index=True, nullable=False)
    full_name = Column(String(255))  
    hashed_password = Column(String(255), nullable=False)