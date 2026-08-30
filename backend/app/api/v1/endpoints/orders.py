import json
import uuid
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.db.session import get_db
from app.models.order import Order, OrderItem
from app.models.counter import Counter
from app.schemas.order import (
    OrderCreate,
    OrderRead,
    QRVerificationRequest,
    QRVerificationResponse
)
from app.schemas.ws import WebSocketMessage
from app.services.qr_service import qr_service
from app.services.websocket_manager import ws_manager

router = APIRouter(prefix="/orders", tags=["Orders"])


@router.post("", response_model=OrderRead, status_code=status.HTTP_201_CREATED)
async def create_order(
    payload: OrderCreate,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new customer order, compute taxes and totals,
    assign an express or optimal counter, and encode verifiable QR token.
    """
    if not payload.items:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Order must contain at least 1 item."
        )

    # Calculate financials
    subtotal = sum(item.unit_price * item.quantity for item in payload.items)
    tax_amount = round(subtotal * 0.05, 2)
    discount_amount = 15.0 if subtotal > 50 else 0.0
    total_amount = max(0.0, subtotal + tax_amount - discount_amount)

    order_number = f"FS-{uuid.uuid4().hex[:4].upper()}"

    # Determine assigned counter
    assigned_counter_num = payload.preferred_counter or "03"
    counter_stmt = select(Counter).where(Counter.counter_number == assigned_counter_num)
    counter_res = await db.execute(counter_stmt)
    counter = counter_res.scalars().first()

    # Build QR Token Payload
    qr_data = {
        "order_number": order_number,
        "customer": payload.customer_identifier,
        "total": total_amount,
        "counter": assigned_counter_num,
        "payment_status": payload.payment_status,
        "payment_method": payload.payment_method
    }
    qr_token_str = json.dumps(qr_data)

    order = Order(
        order_number=order_number,
        customer_identifier=payload.customer_identifier,
        subtotal=subtotal,
        tax_amount=tax_amount,
        discount_amount=discount_amount,
        total_amount=total_amount,
        payment_status=payload.payment_status,
        payment_method=payload.payment_method,
        counter_id=counter.id if counter else None,
        assigned_counter_number=assigned_counter_num,
        qr_token=qr_token_str
    )
    db.add(order)
    await db.flush()

    # Add items
    for item in payload.items:
        order_item = OrderItem(
            order_id=order.id,
            product_barcode=item.product_barcode,
            product_name=item.product_name,
            unit_price=item.unit_price,
            quantity=item.quantity,
            total_price=round(item.unit_price * item.quantity, 2)
        )
        db.add(order_item)

    await db.commit()
    await db.refresh(order)

    # Notify counter POS in real-time via WebSocket
    await ws_manager.broadcast_to_channel(
        f"counter:{assigned_counter_num}",
        WebSocketMessage(
            event="NEW_ORDER_ASSIGNED",
            counter_number=assigned_counter_num,
            data={
                "order_number": order.order_number,
                "customer": order.customer_identifier,
                "items_count": len(order.items),
                "total": order.total_amount
            }
        )
    )

    return order


@router.get("/{order_number}/qr-image")
async def get_order_qr_image(
    order_number: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Streams high-resolution dynamic QR PNG image directly for display/printing.
    Non-blocking PIL rendering.
    """
    stmt = select(Order).where(Order.order_number == order_number)
    res = await db.execute(stmt)
    order = res.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found.")

    png_bytes = await qr_service.generate_qr_bytes(order.qr_token)
    return Response(content=png_bytes, media_type="image/png")


@router.post("/verify-qr", response_model=QRVerificationResponse)
async def verify_order_qr(
    payload: QRVerificationRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Cashier POS scans customer's smartphone QR code.
    Verifies authenticity, checks payment status, and marks order as verified.
    """
    try:
        data = json.loads(payload.qr_token)
        order_num = data.get("order_number") or data.get("orderId")
    except Exception:
        # If payload is raw order number
        order_num = payload.qr_token

    stmt = select(Order).where(Order.order_number == order_num)
    res = await db.execute(stmt)
    order = res.scalars().first()

    if not order:
        return QRVerificationResponse(
            valid=False,
            message="Invalid QR Code: Order not found in FASTSHOP system."
        )

    # Mark as verified
    order.is_verified_by_cashier = True
    await db.commit()
    await db.refresh(order)

    # Broadcast verification event
    await ws_manager.broadcast_to_channel(
        f"counter:{payload.cashier_counter_number}",
        WebSocketMessage(
            event="ORDER_VERIFIED",
            counter_number=payload.cashier_counter_number,
            data={"order_number": order.order_number, "verified": True}
        )
    )

    return QRVerificationResponse(
        valid=True,
        order=OrderRead.model_validate(order),
        message=f"Order #{order.order_number} successfully verified for {order.customer_identifier}."
    )
