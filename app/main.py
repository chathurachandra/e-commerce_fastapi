from fastapi import FastAPI, Depends, HTTPException
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from datetime import datetime, timedelta
from jose import JWTError, jwt
import bcrypt
from app.db.base import Base
from app.db.session import engine, get_db
from app.db.models.user import User
from app.db.models.product import Product
from app.db.models.cart import Cart, CartItem
from app.db.models.order import Order, OrderItem
from app.schemas.user_schema import UserCreate, UserLogin
from app.schemas.product_schema import ProductCreate, ProductResponse
from app.config import SECRET_KEY, ALGORITHM, ACCESS_TOKEN_EXPIRE_MINUTES
from app.ds.inverted_index import InvertedIndex
from app.ds.trie import Trie
from app.ds.lru_cache import LRUCache
app = FastAPI()
security = HTTPBearer()
from app.db.models import *
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
        email = payload.get("sub")
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
    return {"message": "User created", "user_id": new_user.id}
@app.post("/login")
def login_user(user: UserLogin, db: Session = Depends(get_db)):
    db_user = db.query(User).filter(User.email == user.email).first()
    if not db_user or not bcrypt.checkpw(
        user.password.encode("utf-8"),
        db_user.hashed_password.encode("utf-8")
    ):
        raise HTTPException(status_code=401, detail="Invalid credentials")

    access_token = create_access_token(data={"sub": db_user.email})

    return {"access_token": access_token, "token_type": "bearer"}
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
def list_products(skip: int = 0, limit: int = 10, db: Session = Depends(get_db)):
    return db.query(Product).offset(skip).limit(limit).all()
@app.get("/search", response_model=list[ProductResponse])
def search_products(
    q: str,
    skip: int = 0,
    limit: int = 10,
    db: Session = Depends(get_db)
):
    cached = search_cache.get(q)
    if cached:
        return cached
    doc_scores = search_index.search(q)
    if not doc_scores:
        return []
    product_ids = list(doc_scores.keys())
    products = db.query(Product).filter(
        Product.id.in_(product_ids)
    ).all()
    ranked = sorted(
    products,
    key=lambda p: (
        doc_scores[p.id] * 0.6 +
        p.rating * 0.3 +
        (1 / (p.price + 1)) * 0.1
    ),
    reverse=True
)
    search_cache.put(q, ranked)
    return ranked[skip: skip + limit]
@app.get("/autocomplete")
def autocomplete(prefix: str):
    suggestions = autocomplete_trie.search_prefix(prefix)
    return suggestions[:10]
@app.on_event("startup")
def load_products_into_index():
    db_gen = get_db()
    db = next(db_gen)
    try:
        products = db.query(Product).all()
        for product in products:
            text = f"{product.name} {product.description} {product.category}"
            search_index.add_document(product.id, text)
            autocomplete_trie.insert(product.name)
    finally:
        db.close()
    print("Search index loaded.")
def get_or_create_cart(user_id: int, db: Session):
    cart = db.query(Cart).filter(Cart.user_id == user_id).first()
    if not cart:
        cart = Cart(user_id=user_id)
        db.add(cart)
        db.commit()
        db.refresh(cart)
    return cart
@app.post("/cart/add")
def add_to_cart(
    product_id: int,
    quantity: int = 1,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    product = db.query(Product).filter(Product.id == product_id).first()
    if not product:
     raise HTTPException(status_code=404, detail="Product not found")
    cart = get_or_create_cart(current_user.id, db)

    item = db.query(CartItem).filter(
        CartItem.cart_id == cart.id,
        CartItem.product_id == product_id
    ).first()

    if item:
        item.quantity += quantity
    else:
        item = CartItem(
            cart_id=cart.id,
            product_id=product_id,
            quantity=quantity
        )
        db.add(item)

    db.commit()
    return {"message": "Added to cart"}
@app.get("/cart")
def view_cart(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cart = get_or_create_cart(current_user.id, db)
    return db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).all()
@app.post("/checkout")
def checkout(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    cart = get_or_create_cart(current_user.id, db)
    items = db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).all()

    if not items:
        return {"error": "Cart is empty"}

    order = Order(user_id=current_user.id, total_amount=0)
    db.add(order)
    db.commit()
    db.refresh(order)
    total = 0
    for item in items:
        product = db.query(Product).filter(
            Product.id == item.product_id
        ).first()
        total += product.price * item.quantity
        order_item = OrderItem(
            order_id=order.id,
            product_id=item.product_id,
            quantity=item.quantity
        )
        db.add(order_item)
    order.total_amount = total
    db.query(CartItem).filter(
        CartItem.cart_id == cart.id
    ).delete()
    db.commit()
    return {"message": "Order placed", "total": total}
@app.get("/orders")
def get_orders(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    orders = db.query(Order).filter(
        Order.user_id == current_user.id
    ).all()
    response = []
    for order in orders:
        order_data = {
            "order_id": order.id,
            "total_amount": order.total_amount,
            "items": []
        }

        for item in order.items:
            order_data["items"].append({
                "product_id": item.product_id,
                "product_name": item.product.name,
                "quantity": item.quantity
            })
        response.append(order_data)
    return response


