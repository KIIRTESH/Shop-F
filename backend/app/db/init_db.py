import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.models.base import Base
from app.models.product import Product
from app.models.counter import Counter
from app.db.session import engine

logger = logging.getLogger("fastshop.init_db")

SEED_PRODUCTS = [
    {"barcode": "8901058003765", "name": "Maggi 2-Minute Noodles", "price": 56.0, "stock_qty": 150, "category": "Instant Food", "icon": "🍜"},
    {"barcode": "8901063065406", "name": "Britannia Good Day Biscuits", "price": 40.0, "stock_qty": 100, "category": "Biscuits", "icon": "🍪"},
    {"barcode": "8901030810536", "name": "Surf Excel Matic", "price": 210.0, "stock_qty": 80, "category": "Household", "icon": "🧺"},
    {"barcode": "8902519009807", "name": "Classmate Notebook", "price": 35.0, "stock_qty": 50, "category": "Stationery", "icon": "📓"},
    {"barcode": "890103038384", "name": "Amul Taaza Milk 1L", "price": 68.0, "stock_qty": 100, "category": "Dairy", "icon": "🥛"},
    {"barcode": "890171912401", "name": "Britannia Whole Wheat Bread", "price": 45.0, "stock_qty": 80, "category": "Bakery", "icon": "🍞"},
    {"barcode": "544900000099", "name": "Coca-Cola Zero 750ml", "price": 40.0, "stock_qty": 60, "category": "Beverage", "icon": "🥤"},
    {"barcode": "890149110183", "name": "Lay's India's Magic Masala", "price": 30.0, "stock_qty": 120, "category": "Snacks", "icon": "🥔"},
    {"barcode": "890106301201", "name": "Tropicana Orange Juice 1L", "price": 95.0, "stock_qty": 40, "category": "Beverage", "icon": "🍊"},
    {"barcode": "762220172584", "name": "Cadbury Oreo Vanilla 120g", "price": 50.0, "stock_qty": 90, "category": "Biscuits", "icon": "🍪"},
    {"barcode": "890105885264", "name": "Maggi 2-Minute Noodles (4-Pack)", "price": 56.0, "stock_qty": 150, "category": "Instant Food", "icon": "🍜"},
    {"barcode": "890103035821", "name": "Nescafe Classic Coffee 50g", "price": 180.0, "stock_qty": 35, "category": "Beverage", "icon": "☕"}
]

SEED_COUNTERS = [
    {"counter_number": "01", "name": "Checkout Register 01", "is_express": False, "avg_scan_speed_factor": 1.0},
    {"counter_number": "02", "name": "Checkout Register 02", "is_express": False, "avg_scan_speed_factor": 1.1},
    {"counter_number": "03", "name": "Express Lane 03 (<= 5 Items)", "is_express": True, "avg_scan_speed_factor": 1.4},
    {"counter_number": "04", "name": "Checkout Register 04", "is_express": False, "avg_scan_speed_factor": 0.95},
    {"counter_number": "07", "name": "Fast-Track Counter 07", "is_express": True, "avg_scan_speed_factor": 1.3}
]


async def init_db():
    """Initializes database schema and populates/updates store catalog."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    async with AsyncSession(engine) as session:
        # Seed or upsert seed products
        for p in SEED_PRODUCTS:
            res = await session.execute(select(Product).where(Product.barcode == p["barcode"]))
            existing = res.scalars().first()
            if not existing:
                session.add(Product(**p))
            else:
                existing.price = p["price"]
                existing.stock_qty = p.get("stock_qty", existing.stock_qty)
                existing.name = p["name"]
                existing.category = p["category"]
                existing.icon = p["icon"]
                existing.is_active = True

        # Check counters
        for c in SEED_COUNTERS:
            res = await session.execute(select(Counter).where(Counter.counter_number == c["counter_number"]))
            existing_c = res.scalars().first()
            if not existing_c:
                session.add(Counter(**c))

        await session.commit()
