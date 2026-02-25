from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
DATABASE_URL = "mysql+pymysql://dockeruser:dockerpass123@host.docker.internal:3306/ecommerce_db"

engine = create_engine(DATABASE_URL)

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()