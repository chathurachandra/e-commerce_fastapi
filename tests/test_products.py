from fastapi.testclient import TestClient
from app.main import app
import uuid
client = TestClient(app)
def test_products_endpoint_exists():
    response = client.get("/products")
    assert response.status_code == 200
def test_products_pagination():
    response = client.get("/products?page=1&limit=5")
    assert response.status_code == 200
    data = response.json()
    assert "page" in data
    assert "limit" in data
    assert "total" in data
    assert "data" in data
def test_register_user():
    unique_email = f"test_{uuid.uuid4()}@example.com"
    response = client.post("/register", json={
        "email": unique_email,
        "full_name": "Test User",
        "password": "testpassword"
    })

    assert response.status_code == 200
    assert "user_id" in response.json()
def test_login_user():
    unique_email = f"login_{uuid.uuid4()}@example.com"
    client.post("/register", json={
        "email": unique_email,
        "full_name": "Login User",
        "password": "testpassword"
    })

    response = client.post("/login", json={
        "email": unique_email,
        "password": "testpassword"
    })

    assert response.status_code == 200
    assert "access_token" in response.json()


def test_authenticated_product_creation():
    unique_email = f"flow_{uuid.uuid4()}@example.com"
    client.post("/register", json={
        "email": unique_email,
        "full_name": "Flow User",
        "password": "strongpassword"
    })
    login_response = client.post("/login", json={
        "email": unique_email,
        "password": "strongpassword"
    })

    assert login_response.status_code == 200
    token = login_response.json()["access_token"]

    headers = {"Authorization": f"Bearer {token}"}
    product_response = client.post(
        "/products",
        json={
            "name": "Test Product",
            "description": "Test Description",
            "category": "Test",
            "price": 99.99,
            "rating": 4.5
        },
        headers=headers
    )

    assert product_response.status_code == 200
    data = product_response.json()
    assert data["name"] == "Test Product"
def test_cart_and_checkout_flow():
    unique_email = f"cart_{uuid.uuid4()}@example.com"
    client.post("/register", json={
        "email": unique_email,
        "full_name": "Cart User",
        "password": "strongpassword"
    })
    login_response = client.post("/login", json={
        "email": unique_email,
        "password": "strongpassword"
    })

    token = login_response.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    product_response = client.post(
        "/products",
        json={
            "name": "Cart Product",
            "description": "Cart Description",
            "category": "Cart",
            "price": 50.0,
            "rating": 4.0
        },
        headers=headers
    )

    product_id = product_response.json()["id"]
    add_response = client.post(
        f"/cart/add?product_id={product_id}&quantity=2",
        headers=headers
    )
    assert add_response.status_code == 200
    cart_response = client.get("/cart", headers=headers)
    assert cart_response.status_code == 200
    assert len(cart_response.json()) > 0
    checkout_response = client.post("/checkout", headers=headers)
    assert checkout_response.status_code == 200
    assert "total" in checkout_response.json()