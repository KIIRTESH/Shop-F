from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.cart import Cart, CartItem
from app.models.product import Product
from app.schemas.cart import (
    CartRead, 
    CartItemCreate, 
    CartItemUpdate
)

router = APIRouter(prefix="/carts", tags=["Carts"])


async def _get_cart_with_items(db: AsyncSession, cart_id: str) -> Cart:
    """Helper to fetch or create a cart session with fresh items list."""
    stmt = select(Cart).where(Cart.id == cart_id)
    res = await db.execute(stmt)
    cart = res.scalars().first()
    if not cart:
        cart = Cart(id=cart_id, status="ACTIVE")
        db.add(cart)
        await db.commit()
        await db.refresh(cart)

    # Fetch fresh items explicitly from database
    items_stmt = select(CartItem).where(CartItem.cart_id == cart_id).order_by(CartItem.id.asc())
    items_res = await db.execute(items_stmt)
    cart.items = list(items_res.scalars().all())
    return cart


@router.get("/{cart_id}", response_model=CartRead)
async def get_cart(cart_id: str, db: AsyncSession = Depends(get_db)):
    """Retrieve customer cart and its active items."""
    return await _get_cart_with_items(db, cart_id)


@router.post("/{cart_id}/items", response_model=CartRead, status_code=status.HTTP_200_OK)
async def add_item_to_cart(
    cart_id: str,
    payload: CartItemCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Core Barcode Scanner -> PostgreSQL -> Cart integration.
    Looks up barcode in PostgreSQL, validates stock, enforces server-stored price,
    and increments quantity on duplicate scans.
    """
    barcode = payload.barcode.strip()
    if not barcode:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Barcode cannot be empty."
        )

    # 1. Search PostgreSQL products table by barcode
    stmt = select(Product).where(Product.barcode == barcode, Product.is_active == True)
    result = await db.execute(stmt)
    product = result.scalars().first()

    if not product:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Product with barcode '{barcode}' not found."
        )

    # 2. Check out-of-stock
    if product.stock_qty <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Product '{product.name}' is out of stock."
        )

    qty_to_add = max(1, payload.quantity)
    cart = await _get_cart_with_items(db, cart_id)

    # 3. Check if product already exists in customer's cart
    item_stmt = select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_barcode == product.barcode)
    item_res = await db.execute(item_stmt)
    existing_item = item_res.scalars().first()

    if existing_item:
        new_qty = existing_item.quantity + qty_to_add
        if new_qty > product.stock_qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add {qty_to_add} more '{product.name}'. Only {product.stock_qty} available in stock."
            )
        # Increase quantity & enforce database price
        existing_item.quantity = new_qty
        existing_item.unit_price = product.price
        existing_item.product_name = product.name
    else:
        if qty_to_add > product.stock_qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot add {qty_to_add} units. Only {product.stock_qty} available in stock."
            )
        # Add new item with price from PostgreSQL
        new_item = CartItem(
            cart_id=cart.id,
            product_id=product.id,
            product_barcode=product.barcode,
            product_name=product.name,
            unit_price=product.price,
            quantity=qty_to_add,
            category=product.category,
            icon=product.icon
        )
        db.add(new_item)

    await db.commit()
    return await _get_cart_with_items(db, cart_id)


@router.patch("/{cart_id}/items/{barcode}", response_model=CartRead)
async def update_cart_item_quantity(
    cart_id: str,
    barcode: str,
    payload: CartItemUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Updates quantity for an item in the cart (+ / -).
    If target quantity <= 0, deletes the item from the cart.
    """
    stmt = select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_barcode == barcode)
    res = await db.execute(stmt)
    item = res.scalars().first()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Item with barcode '{barcode}' not found in cart."
        )

    if payload.quantity <= 0:
        await db.delete(item)
    else:
        # Check stock in database
        prod_stmt = select(Product).where(Product.barcode == barcode)
        prod_res = await db.execute(prod_stmt)
        product = prod_res.scalars().first()
        if product and payload.quantity > product.stock_qty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Cannot set quantity to {payload.quantity}. Only {product.stock_qty} available in stock."
            )
        item.quantity = payload.quantity
        if product:
            item.unit_price = product.price

    await db.commit()
    return await _get_cart_with_items(db, cart_id)


@router.delete("/{cart_id}/items/{barcode}", response_model=CartRead)
async def remove_cart_item(
    cart_id: str,
    barcode: str,
    db: AsyncSession = Depends(get_db)
):
    """Deletes an item from the customer cart."""
    stmt = select(CartItem).where(CartItem.cart_id == cart_id, CartItem.product_barcode == barcode)
    res = await db.execute(stmt)
    item = res.scalars().first()

    if item:
        await db.delete(item)
        await db.commit()

    return await _get_cart_with_items(db, cart_id)


@router.delete("/{cart_id}", response_model=CartRead)
async def clear_cart(
    cart_id: str,
    db: AsyncSession = Depends(get_db)
):
    """Clears all items in the customer cart."""
    stmt = select(CartItem).where(CartItem.cart_id == cart_id)
    res = await db.execute(stmt)
    items = res.scalars().all()
    for item in items:
        await db.delete(item)
    await db.commit()
    return await _get_cart_with_items(db, cart_id)
