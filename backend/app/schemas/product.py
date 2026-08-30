from pydantic import BaseModel, ConfigDict, computed_field
from typing import Optional


class ProductBase(BaseModel):
    barcode: str
    name: str
    description: Optional[str] = None
    price: float
    category: str = "General"
    icon: str = "📦"
    stock_qty: int = 100


class ProductCreate(ProductBase):
    pass


class ProductRead(ProductBase):
    id: int
    is_active: bool

    @computed_field
    @property
    def stock(self) -> int:
        return self.stock_qty
    
    model_config = ConfigDict(from_attributes=True)
