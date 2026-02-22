from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from app.db.base import Base
from app.db.session import engine, get_db
from app.db.models.user import User
from app.db.models.product import Product
from app.schemas.user_schema import UserCreate, UserLogin
from app.schemas.product_schema import ProductCreate, ProductResponse
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.ds.inverted_index import InvertedIndex
from app.ds.trie import Trie
from app.ds.lru_cache import LRUCache
app = FastAPI()
security = HTTPBearer()
Base.metadata.create_all(bind=engine)
search_index = InvertedIndex()
autocomplete_trie = Trie()
search_cache = LRUCache(capacity=10)
def create_access_token(data: dict):
    to_encode = data.copy()
    expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
):
    token = credentials.credentials
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        email: str = payload.get("sub")
        if email is None:
            raise HTTPException(status_code=401, detail="Invalid token")
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise HTTPException(status_code=401, detail="User not found")
    return user
@app.get("/")
def root():
    return {"message": "API running"}
@app.post("/register")
def register_user(user: UserCreate, db: Session = Depends(get_db)):
    hashed_password = bcrypt.hashpw(
        user.password.encode("utf-8"),
        bcrypt.gensalt()
    ).decode("utf-8")
    new_user = User(
        email=user.email,
        full_name=user.full_name,
        hashed_password=hashed_password
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    return {
        "message": "User created successfully",
        "user_id": new_user.id
    }
@app.post("/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user:
        raise HTTPException(status_code=401, detail="Invalid credentials")
    if not bcrypt.checkpw(
        user.password.encode("utf-8"),
        db_user.hashed_password.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    access_token = create_access_token(data={"sub": db_user.email})
    return {
        "access_token": access_token,
        "token_type": "bearer"
    }
@app.get("/me")
def read_current_user(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "email": current_user.email,
        "full_name": current_user.full_name
    }
@app.post("/products", response_model=ProductResponse)
def create_product(
    product: ProductCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    new_product = Product(
        name=product.name,
        description=product.description,
        category=product.category,
        price=product.price,
        rating=product.rating
    )
    db.add(new_product)
    db.commit()
    db.refresh(new_product)
    text = f"{new_product.name} {new_product.description} {new_product.category}"
    search_index.add_document(new_product.id, text)
    autocomplete_trie.insert(new_product.name)
    return new_product
@app.get("/products", response_model=list[ProductResponse])
def list_products(
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    return db.query(Product).offset(skip).limit(limit).all()
@app.get("/search", response_model=list[ProductResponse])
def search_products(q: str, db: Session = Depends(get_db)):
    cached_result = search_cache.get(q)
    if cached_result:
        return cached_result
    doc_scores = search_index.search(q)
    if not doc_scores:
        return []
    product_ids = list(doc_scores.keys())
    products = db.query(Product).filter(
        Product.id.in_(product_ids)
    ).all()
    ranked_products = sorted(
        products,
        key=lambda p: (doc_scores[p.id], p.rating),
        reverse=True
    )
    search_cache.put(q, ranked_products)
    return ranked_products
@app.get("/autocomplete")
def autocomplete(prefix: str):
    suggestions = autocomplete_trie.search_prefix(prefix)
    return suggestions[:10]
@app.on_event("startup")
def load_products_into_index():
    db = next(get_db())
    products = db.query(Product).all()
    for product in products:
        text = f"{product.name} {product.description} {product.category}"
        search_index.add_document(product.id, text)
        autocomplete_trie.insert(product.name)
    print("Search index + Trie loaded.")