from pydantic import BaseModel
class ProductCreate(BaseModel):
    name: str
    description: str
    category: str
    price: float
    rating: float = 0.0
class ProductResponse(BaseModel):
    id: int
    name: str
    description: str
    category: str
    price: float
    rating: float
    class Config:
        from_attributes = True