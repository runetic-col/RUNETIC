from fastapi import FastAPI, APIRouter, HTTPException, Depends, Query, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from dotenv import load_dotenv
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
import os
import logging
from pathlib import Path
from pydantic import BaseModel, Field, EmailStr, ConfigDict
from typing import List, Optional, Dict, Any
import uuid
from datetime import datetime, timezone, timedelta
from passlib.context import CryptContext
from jose import JWTError, jwt
import httpx
import cloudinary
import cloudinary.uploader

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

# MongoDB connection
mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Security
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
security = HTTPBearer()
SECRET_KEY = os.environ["SECRET_KEY"]
ALGORITHM = "HS256"
ADMIN_PASSWORD = os.environ["ADMIN_PASSWORD"]
MAYORISTA_PASSWORD = os.environ["MAYORISTA_PASSWORD"]
WHATSAPP_PHONE = os.environ.get("WHATSAPP_PHONE", "573104704077")

# Cloudinary config
cloudinary.config(
    cloud_name=os.environ["CLOUDINARY_CLOUD_NAME"],
    api_key=os.environ["CLOUDINARY_API_KEY"],
    api_secret=os.environ.get("CLOUDINARY_API_SECRET", "")
)

# WOMPI config
WOMPI_PUBLIC_KEY = os.environ.get("WOMPI_PUBLIC_KEY", "")
WOMPI_PRIVATE_KEY = os.environ.get("WOMPI_PRIVATE_KEY", "")  # Required for production - integrity signature
WOMPI_API_BASE_URL = os.environ.get("WOMPI_API_BASE_URL", "https://sandbox.wompi.co/v1")

import hashlib
import random

app = FastAPI(title="RUNETIC E-Commerce API")
api_router = APIRouter(prefix="/api")

# ==================== BARCODE GENERATION ====================

def calculate_ean13_check_digit(code_12: str) -> str:
    """Calculate the check digit for EAN-13 barcode"""
    total = 0
    for i, digit in enumerate(code_12):
        if i % 2 == 0:
            total += int(digit)
        else:
            total += int(digit) * 3
    check = (10 - (total % 10)) % 10
    return str(check)

async def generate_unique_barcode() -> str:
    """Generate a unique EAN-13 barcode for RUNETIC products
    
    Format: 770XXXXXXXXXX (770 = Colombia country code prefix for internal use)
    """
    max_attempts = 100
    for _ in range(max_attempts):
        # 770 prefix (Colombia) + 9 random digits + check digit
        base_code = "770" + "".join([str(random.randint(0, 9)) for _ in range(9)])
        check_digit = calculate_ean13_check_digit(base_code)
        barcode = base_code + check_digit
        
        # Check if barcode already exists in database
        existing = await db.products.find_one({"barcode": barcode})
        if not existing:
            return barcode
    
    # Fallback: use timestamp-based barcode
    timestamp = str(int(datetime.now(timezone.utc).timestamp()))[-9:]
    base_code = "770" + timestamp
    check_digit = calculate_ean13_check_digit(base_code)
    return base_code + check_digit

async def generate_unique_product_code() -> str:
    """Generate a unique product code like RUN-001, RUN-002, etc."""
    # Get the highest existing code number
    pipeline = [
        {"$match": {"code": {"$regex": "^RUN-\\d+$"}}},
        {"$project": {"num": {"$toInt": {"$substr": ["$code", 4, -1]}}}},
        {"$sort": {"num": -1}},
        {"$limit": 1}
    ]
    result = await db.products.aggregate(pipeline).to_list(length=1)
    
    if result:
        next_num = result[0]["num"] + 1
    else:
        # Count all products and start from there
        count = await db.products.count_documents({})
        next_num = count + 1
    
    return f"RUN-{next_num:04d}"

def generate_pickup_token():
    """Generate a unique 8-character alphanumeric token for cash on delivery"""
    import string
    chars = string.ascii_uppercase + string.digits
    token = ''.join(random.choices(chars, k=8))
    return f"COD-{token}"

async def send_pickup_token_email(email: str, customer_name: str, order_number: str, token: str, total: float):
    """Send pickup token via email (placeholder - integrate with email service)"""
    # For now, we'll log this and store in database
    # In production, integrate with SendGrid, Resend, or similar
    email_log = {
        "to": email,
        "subject": f"RUNETIC - Tu código de entrega #{order_number}",
        "body": f"""
Hola {customer_name},

Gracias por tu compra en RUNETIC.

Tu código de entrega es: {token}

IMPORTANTE: Este código es necesario para reclamar tu pedido.
SIN ESTE CÓDIGO NO SE ENTREGARÁ EL PRODUCTO.

Detalles del pedido:
- Número de orden: {order_number}
- Total a pagar: ${total:,.0f} COP

Guarda este correo en un lugar seguro.

Equipo RUNETIC
        """,
        "sent_at": datetime.now(timezone.utc).isoformat(),
        "order_number": order_number,
        "token": token
    }
    await db.email_logs.insert_one(email_log)
    logging.info(f"Pickup token email logged for order {order_number}: {token}")
    return True

# ==================== MODELS ====================

class ProductVersion(BaseModel):
    version_type: str  # hombre_fan, hombre_jugador, dama, nino
    base_price: float
    
class ProductCustomization(BaseModel):
    estampado: str  # sin_estampado, estandar, personalizado
    estampado_price: float = 0
    parches: str  # sin_parches, con_parches
    parches_price: float = 0
    empaque: str  # normal, premium
    empaque_price: float = 0

class SizeChart(BaseModel):
    version_type: str
    sizes: Dict[str, Dict[str, str]]  # {"S": {"width": "49-51cm", "length": "67-69cm"}}

class Product(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    barcode: Optional[str] = None  # Código de barras EAN-13 único
    reference: str
    category: str  # futbol, nfl, baseball, formula1
    team: str
    base_price_retail: float
    base_price_wholesale: float
    original_price: Optional[float] = None  # Precio original antes del descuento
    versions: List[ProductVersion] = []
    available_sizes: List[str] = []  # ["S", "M", "L", "XL", "2XL"]
    size_charts: List[SizeChart] = []
    images: Dict[str, List[str]] = {}  # {"fan": ["url1", "url2"], "jugador": ["url3"]}
    stock: Dict[str, Dict[str, int]] = {}  # {"hombre_fan": {"S": 10, "M": 15}}
    active: bool = True
    is_featured: bool = False  # Producto destacado
    is_on_sale: bool = False  # Producto en oferta
    is_seasonal: bool = False  # Promoción por temporada
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

class ProductCreate(BaseModel):
    code: Optional[str] = None  # Will be auto-generated if not provided
    reference: str
    category: str
    team: str
    base_price_retail: float
    base_price_wholesale: float
    original_price: Optional[float] = None
    images: Optional[Dict[str, List[str]]] = None
    available_versions: Optional[List[str]] = None
    available_sizes_by_version: Optional[Dict[str, List[str]]] = None
    available_colors: Optional[List[str]] = None
    packaging_config: Optional[List[Dict]] = None
    is_featured: bool = False
    is_on_sale: bool = False
    is_seasonal: bool = False

class InventoryEntry(BaseModel):
    product_code: str
    version_type: str
    size: str
    quantity: int
    entry_price: float
    entry_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None

class InventoryExit(BaseModel):
    product_code: str
    version_type: str
    size: str
    quantity: int
    exit_price: float
    exit_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    order_id: Optional[str] = None

# ==================== BATCH INVENTORY & PROFITABILITY ====================

class BatchEntry(BaseModel):
    """Model for tracking inventory batches with cost and profitability analysis"""
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    barcode: str  # Product barcode for identification
    product_code: Optional[str] = None  # Optional product code reference
    product_name: Optional[str] = None  # Product name/description
    gender: str  # hombre, mujer, nino, unisex
    garment_type: str  # camiseta, pantalon, shorts, chaqueta, etc.
    team: Optional[str] = None  # Team/brand associated
    quantity: int  # Number of items in this batch
    entry_price: float  # Cost per unit (precio de entrada)
    selling_price: float  # Intended selling price per unit (precio de salida)
    total_investment: float = 0  # Calculated: quantity * entry_price
    projected_revenue: float = 0  # Calculated: quantity * selling_price
    projected_profit: float = 0  # Calculated: projected_revenue - total_investment
    profit_margin_percent: float = 0  # Calculated: (profit / investment) * 100
    entry_date: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None
    status: str = "active"  # active, sold, partial, cancelled

class BatchEntryCreate(BaseModel):
    barcode: str
    product_code: Optional[str] = None
    product_name: Optional[str] = None
    gender: str
    garment_type: str
    team: Optional[str] = None
    quantity: int
    entry_price: float
    selling_price: float
    notes: Optional[str] = None

class DiscountCode(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    code: str
    discount_type: str  # percentage, fixed
    discount_value: float
    code_type: str  # normal, authorized
    max_uses: Optional[int] = None  # None for unlimited
    current_uses: int = 0
    used_by: List[Dict[str, str]] = []  # [{"name": "Juan", "email": "x", "phone": "x"}]
    creator_name: Optional[str] = None  # For authorized codes
    valid_from: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    valid_until: Optional[datetime] = None
    active: bool = True

class CartItem(BaseModel):
    product_id: str
    product_code: str
    product_name: str
    version_type: str
    size: str
    quantity: int
    customization: ProductCustomization
    unit_price: float
    total_price: float

class ShippingAddress(BaseModel):
    full_name: str
    document_type: str  # CC, CE, NIT, TI, PP
    document_id: str
    phone: str
    email: EmailStr
    address: str
    city: str
    department: str
    postal_code: Optional[str] = None

class Order(BaseModel):
    model_config = ConfigDict(extra="ignore")
    
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    order_number: str = Field(default_factory=lambda: f"ORD-{datetime.now().strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}")
    customer_type: str  # retail, wholesale
    items: List[CartItem]
    subtotal: float
    discount_code: Optional[str] = None
    discount_amount: float = 0
    shipping_cost: float = 0
    total_amount: float
    shipping_address: ShippingAddress
    payment_method: str  # pse, credit_card, bank_transfer, cash_on_delivery
    payment_status: str = "pending"  # pending, paid, failed
    order_status: str = "pending"  # pending, confirmed, processing, shipped, delivered, cancelled
    size_confirmation: bool = False  # User confirmed size selection
    whatsapp_sent: bool = False
    pickup_token: Optional[str] = None  # Token for cash on delivery pickup
    pickup_token_used: bool = False  # If token has been used to claim product
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    notes: Optional[str] = None

class OrderCreate(BaseModel):
    customer_type: str
    items: List[CartItem]
    shipping_address: ShippingAddress
    payment_method: str
    discount_code: Optional[str] = None
    size_confirmation: bool
    shipping_cost: Optional[float] = None
    subtotal: Optional[float] = None
    total_amount: Optional[float] = None

class User(BaseModel):
    username: str
    role: str  # admin, mayorista
    hashed_password: str

# ==================== AUTH ====================

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + (expires_delta or timedelta(hours=24))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    try:
        token = credentials.credentials
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise HTTPException(status_code=401, detail="Invalid credentials")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid credentials")

# ==================== ROUTES ====================

@api_router.post("/auth/login")
async def login(username: str = Body(...), password: str = Body(...)):
    # Check fixed passwords from environment
    if username == "Runetic.col" and password == ADMIN_PASSWORD:
        token = create_access_token({"sub": username, "role": "admin"})
        return {"access_token": token, "token_type": "bearer", "role": "admin"}
    elif username == "RuneticMayorista" and password == MAYORISTA_PASSWORD:
        token = create_access_token({"sub": username, "role": "mayorista"})
        return {"access_token": token, "token_type": "bearer", "role": "mayorista"}
    raise HTTPException(status_code=401, detail="Invalid credentials")

# Products
@api_router.get("/products")
async def get_products(
    category: Optional[str] = None,
    team: Optional[str] = None,
    search: Optional[str] = None,
    skip: int = 0,
    limit: int = 50
):
    query = {"active": True}
    if category:
        query["category"] = category
    if team:
        query["team"] = team
    if search:
        query["$or"] = [
            {"reference": {"$regex": search, "$options": "i"}},
            {"team": {"$regex": search, "$options": "i"}}
        ]
    
    # Optimize: Only fetch required fields - include all config fields for editing
    projection = {
        "_id": 0, "id": 1, "code": 1, "barcode": 1, "reference": 1, "category": 1, 
        "team": 1, "base_price_retail": 1, "base_price_wholesale": 1, 
        "original_price": 1, "images": 1, "available_sizes": 1, "packaging_config": 1,
        "packaging_options": 1, "available_versions": 1, 
        "available_sizes_by_version": 1, "available_colors": 1,
        "is_featured": 1, "is_on_sale": 1, "is_seasonal": 1
    }
    
    products = await db.products.find(query, projection).skip(skip).limit(limit).to_list(length=limit)
    total = await db.products.count_documents(query)
    return {"products": products, "total": total}

@api_router.get("/products/featured/list")
async def get_featured_products():
    """Get products marked as featured"""
    projection = {"_id": 0, "id": 1, "reference": 1, "team": 1, "category": 1, 
                  "base_price_retail": 1, "original_price": 1, "images": 1, "is_featured": 1, "is_on_sale": 1}
    products = await db.products.find(
        {"active": True, "is_featured": True}, projection
    ).limit(12).to_list(length=12)
    return {"products": products}

@api_router.get("/products/on-sale/list")
async def get_on_sale_products():
    """Get products marked as on sale"""
    projection = {"_id": 0, "id": 1, "reference": 1, "team": 1, "category": 1, 
                  "base_price_retail": 1, "original_price": 1, "images": 1, "is_on_sale": 1}
    products = await db.products.find(
        {"active": True, "is_on_sale": True}, projection
    ).limit(12).to_list(length=12)
    return {"products": products}

@api_router.get("/products/seasonal/list")
async def get_seasonal_products():
    """Get products marked as seasonal promotion"""
    projection = {"_id": 0, "id": 1, "reference": 1, "team": 1, "category": 1, 
                  "base_price_retail": 1, "original_price": 1, "images": 1, "is_seasonal": 1, "is_on_sale": 1}
    products = await db.products.find(
        {"active": True, "is_seasonal": True}, projection
    ).limit(12).to_list(length=12)
    return {"products": products}

@api_router.get("/products/suggestions/{product_id}")
async def get_product_suggestions(product_id: str):
    """Get product suggestions based on most purchased or related products"""
    # First, get the current product to know its category
    current_product = await db.products.find_one({"id": product_id}, {"_id": 0, "category": 1, "team": 1})
    
    # Try to get most purchased products from orders
    pipeline = [
        {"$unwind": "$items"},
        {"$group": {"_id": "$items.product_id", "purchase_count": {"$sum": "$items.quantity"}}},
        {"$sort": {"purchase_count": -1}},
        {"$limit": 20}
    ]
    
    most_purchased = await db.orders.aggregate(pipeline).to_list(length=20)
    most_purchased_ids = [item["_id"] for item in most_purchased if item["_id"] != product_id]
    
    projection = {"_id": 0, "id": 1, "reference": 1, "team": 1, "category": 1, 
                  "base_price_retail": 1, "original_price": 1, "images": 1, "is_on_sale": 1}
    
    suggestions = []
    
    # Get products from most purchased list
    if most_purchased_ids:
        purchased_products = await db.products.find(
            {"id": {"$in": most_purchased_ids[:8]}, "active": True}, projection
        ).to_list(length=8)
        suggestions.extend(purchased_products)
    
    # If not enough, add related products (same category or team)
    if len(suggestions) < 8 and current_product:
        related = await db.products.find(
            {
                "active": True,
                "id": {"$ne": product_id, "$nin": [s["id"] for s in suggestions]},
                "$or": [
                    {"category": current_product.get("category")},
                    {"team": current_product.get("team")}
                ]
            }, projection
        ).limit(8 - len(suggestions)).to_list(length=8 - len(suggestions))
        suggestions.extend(related)
    
    # If still not enough, add random products
    if len(suggestions) < 8:
        random_products = await db.products.find(
            {"active": True, "id": {"$ne": product_id, "$nin": [s["id"] for s in suggestions]}}, 
            projection
        ).limit(8 - len(suggestions)).to_list(length=8 - len(suggestions))
        suggestions.extend(random_products)
    
    return {"products": suggestions[:8]}

@api_router.get("/products/{product_id}")
async def get_product(product_id: str):
    product = await db.products.find_one({"id": product_id}, {"_id": 0})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return product

@api_router.post("/products", dependencies=[Depends(get_current_user)])
async def create_product(product: ProductCreate, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Generate unique product code if not provided
    product_code = product.code
    if not product_code:
        product_code = await generate_unique_product_code()
    
    # Generate unique barcode (EAN-13)
    barcode = await generate_unique_barcode()
    
    # Build product data
    product_data = {
        "id": str(uuid.uuid4()),
        "code": product_code,
        "barcode": barcode,
        "reference": product.reference,
        "category": product.category,
        "team": product.team,
        "base_price_retail": product.base_price_retail,
        "base_price_wholesale": product.base_price_wholesale,
        "original_price": product.original_price,
        "images": product.images or {"fan": [], "player": []},
        "available_versions": product.available_versions or ["hombre_fan", "hombre_jugador", "dama_fan", "nino"],
        "available_sizes_by_version": product.available_sizes_by_version or {},
        "available_colors": product.available_colors or [],
        "packaging_config": product.packaging_config or [
            {"id": "none", "name": "Sin Caja", "price": 0, "enabled": True},
            {"id": "normal", "name": "Caja Normal", "price": 5000, "enabled": True},
            {"id": "premium", "name": "Caja Premium", "price": 10000, "enabled": True}
        ],
        "stock": {},
        "active": True,
        "is_featured": product.is_featured,
        "is_on_sale": product.is_on_sale,
        "is_seasonal": product.is_seasonal,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.products.insert_one(product_data)
    
    return {
        "message": "Product created", 
        "id": product_data["id"],
        "code": product_data["code"],
        "barcode": product_data["barcode"]
    }

@api_router.put("/products/{product_id}", dependencies=[Depends(get_current_user)])
async def update_product(product_id: str, product_data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.products.update_one({"id": product_id}, {"$set": product_data})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product updated"}

@api_router.delete("/products/{product_id}", dependencies=[Depends(get_current_user)])
async def delete_product(product_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.products.update_one({"id": product_id}, {"$set": {"active": False}})
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Product not found")
    return {"message": "Product deleted"}

# Orders
@api_router.post("/orders")
async def create_order(order: OrderCreate):
    # Validate discount code if provided
    discount_amount = 0
    if order.discount_code:
        code = await db.discount_codes.find_one({"code": order.discount_code, "active": True}, {"_id": 0})
        if not code:
            raise HTTPException(status_code=400, detail="Invalid discount code")
        
        # Check if code is still valid
        if code.get("valid_until") and datetime.fromisoformat(code["valid_until"]) < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="Discount code expired")
        
        # Check usage limit
        if code.get("max_uses") and code["current_uses"] >= code["max_uses"]:
            raise HTTPException(status_code=400, detail="Discount code limit reached")
        
        # Check if normal code already used by this customer
        if code["code_type"] == "normal":
            customer_data = f"{order.shipping_address.full_name}|{order.shipping_address.phone}|{order.shipping_address.address}"
            for used in code.get("used_by", []):
                if f"{used['name']}|{used['phone']}|{used['address']}" == customer_data:
                    raise HTTPException(status_code=400, detail="You have already used this discount code")
        
        # Calculate discount
        subtotal = sum(item.total_price for item in order.items)
        if code["discount_type"] == "percentage":
            discount_amount = subtotal * (code["discount_value"] / 100)
        else:
            discount_amount = code["discount_value"]
    
    # Calculate totals
    subtotal = sum(item.total_price for item in order.items)
    total_units = sum(item.quantity for item in order.items)
    
    # Envío: $15,000 COP, GRATIS a partir de 6 unidades SOLO PARA RETAIL
    # MAYORISTA: NUNCA tiene envío gratis
    SHIPPING_COST = 15000
    FREE_SHIPPING_MIN_UNITS = 6
    
    # Determinar si es mayorista
    is_wholesale = order.customer_type == "wholesale"
    
    # Si el frontend envía shipping_cost, usarlo; si no, calcularlo
    if hasattr(order, 'shipping_cost') and order.shipping_cost is not None:
        shipping_cost = order.shipping_cost
    else:
        # MAYORISTA: Siempre cobra envío
        # RETAIL: Envío gratis a partir de 6 unidades
        if is_wholesale:
            shipping_cost = SHIPPING_COST  # Mayorista SIEMPRE paga envío
        else:
            shipping_cost = 0 if total_units >= FREE_SHIPPING_MIN_UNITS else SHIPPING_COST
    
    total = subtotal - discount_amount + shipping_cost
    
    # Create order dict without conflicting fields from input
    order_data = order.dict(exclude={'subtotal', 'shipping_cost', 'total_amount', 'discount_amount'}, exclude_none=False)
    
    # Build order manually to avoid conflicts
    order_obj = Order(
        customer_type=order_data['customer_type'],
        items=order_data['items'],
        shipping_address=order_data['shipping_address'],
        payment_method=order_data['payment_method'],
        discount_code=order_data.get('discount_code'),
        size_confirmation=order_data.get('size_confirmation', False),
        subtotal=subtotal,
        discount_amount=discount_amount,
        shipping_cost=shipping_cost,
        total_amount=total
    )
    order_dict = order_obj.dict()
    
    order_dict["created_at"] = order_dict["created_at"].isoformat()
    order_dict["updated_at"] = order_dict["updated_at"].isoformat()
    
    # Generate pickup token for cash on delivery
    pickup_token = None
    if order.payment_method == "cash_on_delivery":
        pickup_token = generate_pickup_token()
        order_dict["pickup_token"] = pickup_token
        order_dict["pickup_token_used"] = False
        # Send token via email
        await send_pickup_token_email(
            email=order.shipping_address.email,
            customer_name=order.shipping_address.full_name,
            order_number=order_dict["order_number"],
            token=pickup_token,
            total=total
        )
    
    await db.orders.insert_one(order_dict)
    
    # Update discount code usage
    if order.discount_code:
        await db.discount_codes.update_one(
            {"code": order.discount_code},
            {
                "$inc": {"current_uses": 1},
                "$push": {
                    "used_by": {
                        "name": order.shipping_address.full_name,
                        "email": order.shipping_address.email,
                        "phone": order.shipping_address.phone,
                        "address": order.shipping_address.address
                    }
                }
            }
        )
    
    # Update inventory using bulk operations for better performance
    from pymongo import UpdateOne
    bulk_operations = [
        UpdateOne(
            {"code": item.product_code},
            {"$inc": {f"stock.{item.version_type}.{item.size}": -item.quantity}}
        )
        for item in order.items
    ]
    if bulk_operations:
        await db.products.bulk_write(bulk_operations)
    
    return {
        "message": "Order created", 
        "order_id": order_dict["id"], 
        "order_number": order_dict["order_number"],
        "pickup_token": pickup_token  # Will be None for non-COD orders
    }

@api_router.get("/orders")
async def get_orders(
    status: Optional[str] = None,
    skip: int = 0,
    limit: int = 50,
    current_user: dict = Depends(get_current_user)
):
    query = {}
    if status:
        query["order_status"] = status
    
    orders = await db.orders.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    total = await db.orders.count_documents(query)
    return {"orders": orders, "total": total}

@api_router.get("/orders/{order_id}")
async def get_order(order_id: str):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    return order

@api_router.post("/orders/validate-pickup-token")
async def validate_pickup_token(data: Dict[str, str] = Body(...)):
    """Validate pickup token for cash on delivery orders"""
    token = data.get("token", "").strip().upper()
    order_number = data.get("order_number", "").strip().upper()
    
    if not token:
        raise HTTPException(status_code=400, detail="Token requerido")
    
    query = {"pickup_token": token}
    if order_number:
        query["order_number"] = order_number
    
    order = await db.orders.find_one(query, {"_id": 0})
    
    if not order:
        raise HTTPException(status_code=404, detail="Token inválido o no encontrado")
    
    if order.get("pickup_token_used"):
        raise HTTPException(status_code=400, detail="Este token ya fue utilizado")
    
    return {
        "valid": True,
        "order_number": order["order_number"],
        "customer_name": order["shipping_address"]["full_name"],
        "total_amount": order["total_amount"],
        "items_count": sum(item["quantity"] for item in order["items"])
    }

@api_router.post("/orders/{order_id}/use-pickup-token", dependencies=[Depends(get_current_user)])
async def use_pickup_token(order_id: str, current_user: dict = Depends(get_current_user)):
    """Mark pickup token as used when product is delivered"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    order = await db.orders.find_one({"id": order_id})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    if order.get("payment_method") != "cash_on_delivery":
        raise HTTPException(status_code=400, detail="Esta orden no es contra entrega")
    
    if order.get("pickup_token_used"):
        raise HTTPException(status_code=400, detail="El token ya fue utilizado")
    
    await db.orders.update_one(
        {"id": order_id},
        {
            "$set": {
                "pickup_token_used": True,
                "payment_status": "paid",
                "order_status": "delivered",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }
        }
    )
    
    return {"message": "Token validado y pedido entregado"}

@api_router.put("/orders/{order_id}/status", dependencies=[Depends(get_current_user)])
async def update_order_status(
    order_id: str,
    status: str = Body(..., embed=True),
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Update both order_status and payment_status based on the status
    update_fields = {
        "updated_at": datetime.now(timezone.utc).isoformat()
    }
    
    # Map frontend status to backend fields
    if status in ['pending', 'paid', 'failed', 'confirmed']:
        update_fields["payment_status"] = status
        if status == 'paid':
            update_fields["order_status"] = 'confirmed'
        elif status == 'confirmed':
            update_fields["order_status"] = 'processing'
    elif status == 'delivered':
        update_fields["order_status"] = 'delivered'
        update_fields["payment_status"] = 'paid'
    elif status == 'cancelled':
        update_fields["order_status"] = 'cancelled'
        update_fields["payment_status"] = 'cancelled'
    else:
        update_fields["order_status"] = status
    
    result = await db.orders.update_one(
        {"id": order_id},
        {"$set": update_fields}
    )
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order status updated", "status": status}

@api_router.delete("/orders/{order_id}", dependencies=[Depends(get_current_user)])
async def delete_order(order_id: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.orders.delete_one({"id": order_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Order not found")
    return {"message": "Order deleted successfully"}

# Discount Codes
@api_router.post("/discount-codes", dependencies=[Depends(get_current_user)])
async def create_discount_code(code: DiscountCode, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    code_dict = code.dict()
    code_dict["valid_from"] = code_dict["valid_from"].isoformat()
    if code_dict.get("valid_until"):
        code_dict["valid_until"] = code_dict["valid_until"].isoformat()
    
    await db.discount_codes.insert_one(code_dict)
    return {"message": "Discount code created"}

@api_router.get("/discount-codes")
async def get_discount_codes(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    codes = await db.discount_codes.find({}, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    total = await db.discount_codes.count_documents({})
    return {"codes": codes, "total": total}

@api_router.post("/discount-codes/validate")
async def validate_discount_code(data: Dict[str, str] = Body(...)):
    code = data.get("code", "")
    code_doc = await db.discount_codes.find_one({"code": code, "active": True}, {"_id": 0})
    if not code_doc:
        raise HTTPException(status_code=404, detail="Código de descuento inválido")
    
    if code_doc.get("valid_until") and datetime.fromisoformat(code_doc["valid_until"]) < datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail="Código de descuento expirado")
    
    if code_doc.get("max_uses") and code_doc["current_uses"] >= code_doc["max_uses"]:
        raise HTTPException(status_code=400, detail="Código de descuento agotado")
    
    return {"valid": True, "discount_type": code_doc["discount_type"], "discount_value": code_doc["discount_value"]}

# Inventory
@api_router.post("/inventory/entry", dependencies=[Depends(get_current_user)])
async def add_inventory_entry(entry: InventoryEntry, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    entry_dict = entry.dict()
    entry_dict["entry_date"] = entry_dict["entry_date"].isoformat()
    await db.inventory_entries.insert_one(entry_dict)
    
    # Update product stock
    await db.products.update_one(
        {"code": entry.product_code},
        {"$inc": {f"stock.{entry.version_type}.{entry.size}": entry.quantity}}
    )
    
    return {"message": "Inventory entry added"}

@api_router.get("/inventory/entries")
async def get_inventory_entries(
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    entries = await db.inventory_entries.find({}, {"_id": 0}).sort("entry_date", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.inventory_entries.count_documents({})
    return {"entries": entries, "total": total}

# ==================== BATCH INVENTORY & PROFITABILITY ENDPOINTS ====================

@api_router.post("/inventory/batches", dependencies=[Depends(get_current_user)])
async def create_batch_entry(batch: BatchEntryCreate, current_user: dict = Depends(get_current_user)):
    """Create a new inventory batch entry with profitability calculations"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Calculate profitability metrics
    total_investment = batch.quantity * batch.entry_price
    projected_revenue = batch.quantity * batch.selling_price
    projected_profit = projected_revenue - total_investment
    profit_margin_percent = (projected_profit / total_investment * 100) if total_investment > 0 else 0
    
    batch_entry = BatchEntry(
        barcode=batch.barcode,
        product_code=batch.product_code,
        product_name=batch.product_name,
        gender=batch.gender,
        garment_type=batch.garment_type,
        team=batch.team,
        quantity=batch.quantity,
        entry_price=batch.entry_price,
        selling_price=batch.selling_price,
        total_investment=total_investment,
        projected_revenue=projected_revenue,
        projected_profit=projected_profit,
        profit_margin_percent=round(profit_margin_percent, 2),
        notes=batch.notes
    )
    
    batch_dict = batch_entry.dict()
    batch_dict["entry_date"] = batch_dict["entry_date"].isoformat()
    
    await db.inventory_batches.insert_one(batch_dict)
    
    return {
        "message": "Batch entry created",
        "id": batch_dict["id"],
        "total_investment": total_investment,
        "projected_revenue": projected_revenue,
        "projected_profit": projected_profit,
        "profit_margin_percent": round(profit_margin_percent, 2)
    }

@api_router.get("/inventory/batches", dependencies=[Depends(get_current_user)])
async def get_batch_entries(
    skip: int = 0,
    limit: int = 100,
    barcode: Optional[str] = None,
    gender: Optional[str] = None,
    garment_type: Optional[str] = None,
    status: Optional[str] = None,
    current_user: dict = Depends(get_current_user)
):
    """Get all batch entries with optional filters"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = {}
    if barcode:
        query["barcode"] = barcode
    if gender:
        query["gender"] = gender
    if garment_type:
        query["garment_type"] = garment_type
    if status:
        query["status"] = status
    
    batches = await db.inventory_batches.find(query, {"_id": 0}).sort("entry_date", -1).skip(skip).limit(limit).to_list(length=limit)
    total = await db.inventory_batches.count_documents(query)
    
    # Calculate totals
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "total_investment": {"$sum": "$total_investment"},
            "total_projected_revenue": {"$sum": "$projected_revenue"},
            "total_projected_profit": {"$sum": "$projected_profit"},
            "total_units": {"$sum": "$quantity"}
        }}
    ]
    
    totals = await db.inventory_batches.aggregate(pipeline).to_list(length=1)
    summary = totals[0] if totals else {
        "total_investment": 0,
        "total_projected_revenue": 0,
        "total_projected_profit": 0,
        "total_units": 0
    }
    
    # Calculate overall profit margin
    if summary["total_investment"] > 0:
        summary["overall_profit_margin"] = round(
            (summary["total_projected_profit"] / summary["total_investment"]) * 100, 2
        )
    else:
        summary["overall_profit_margin"] = 0
    
    return {
        "batches": batches,
        "total": total,
        "summary": summary
    }

@api_router.get("/inventory/batches/{batch_id}", dependencies=[Depends(get_current_user)])
async def get_batch_entry(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Get a single batch entry by ID"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    batch = await db.inventory_batches.find_one({"id": batch_id}, {"_id": 0})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return batch

@api_router.put("/inventory/batches/{batch_id}", dependencies=[Depends(get_current_user)])
async def update_batch_entry(
    batch_id: str,
    update_data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    """Update a batch entry - recalculates profitability if prices/quantity change"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    batch = await db.inventory_batches.find_one({"id": batch_id})
    if not batch:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    # Recalculate if quantity or prices changed
    quantity = update_data.get("quantity", batch.get("quantity", 0))
    entry_price = update_data.get("entry_price", batch.get("entry_price", 0))
    selling_price = update_data.get("selling_price", batch.get("selling_price", 0))
    
    total_investment = quantity * entry_price
    projected_revenue = quantity * selling_price
    projected_profit = projected_revenue - total_investment
    profit_margin_percent = (projected_profit / total_investment * 100) if total_investment > 0 else 0
    
    update_data["total_investment"] = total_investment
    update_data["projected_revenue"] = projected_revenue
    update_data["projected_profit"] = projected_profit
    update_data["profit_margin_percent"] = round(profit_margin_percent, 2)
    update_data["updated_at"] = datetime.now(timezone.utc).isoformat()
    
    await db.inventory_batches.update_one({"id": batch_id}, {"$set": update_data})
    
    return {
        "message": "Batch updated",
        "total_investment": total_investment,
        "projected_revenue": projected_revenue,
        "projected_profit": projected_profit,
        "profit_margin_percent": round(profit_margin_percent, 2)
    }

@api_router.delete("/inventory/batches/{batch_id}", dependencies=[Depends(get_current_user)])
async def delete_batch_entry(batch_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a batch entry"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.inventory_batches.delete_one({"id": batch_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Batch not found")
    
    return {"message": "Batch deleted"}

@api_router.get("/inventory/batches/barcode/{barcode}", dependencies=[Depends(get_current_user)])
async def get_batches_by_barcode(barcode: str, current_user: dict = Depends(get_current_user)):
    """Get all batch entries for a specific barcode with profitability summary"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    batches = await db.inventory_batches.find({"barcode": barcode}, {"_id": 0}).sort("entry_date", -1).to_list(length=100)
    
    if not batches:
        return {"batches": [], "summary": None}
    
    # Calculate totals for this barcode
    total_investment = sum(b.get("total_investment", 0) for b in batches)
    total_revenue = sum(b.get("projected_revenue", 0) for b in batches)
    total_profit = sum(b.get("projected_profit", 0) for b in batches)
    total_units = sum(b.get("quantity", 0) for b in batches)
    
    summary = {
        "barcode": barcode,
        "total_batches": len(batches),
        "total_units": total_units,
        "total_investment": total_investment,
        "total_projected_revenue": total_revenue,
        "total_projected_profit": total_profit,
        "overall_profit_margin": round((total_profit / total_investment * 100), 2) if total_investment > 0 else 0,
        "avg_entry_price": round(total_investment / total_units, 2) if total_units > 0 else 0,
        "avg_selling_price": round(total_revenue / total_units, 2) if total_units > 0 else 0
    }
    
    return {"batches": batches, "summary": summary}

# Settings - Wholesale Tiers
@api_router.get("/settings/wholesale-tiers")
async def get_wholesale_tiers(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    settings = await db.settings.find_one({"key": "wholesale_tiers"}, {"_id": 0})
    if settings:
        return {"tiers": settings.get("value", [])}
    
    # Default tiers
    default_tiers = [
        {"min_quantity": 1, "max_quantity": 9, "discount_percent": 30},
        {"min_quantity": 10, "max_quantity": 19, "discount_percent": 35},
        {"min_quantity": 20, "max_quantity": 49, "discount_percent": 40},
        {"min_quantity": 50, "max_quantity": None, "discount_percent": 45}
    ]
    return {"tiers": default_tiers}

@api_router.put("/settings/wholesale-tiers")
async def update_wholesale_tiers(
    data: Dict[str, Any],
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    tiers = data.get("tiers", [])
    
    await db.settings.update_one(
        {"key": "wholesale_tiers"},
        {"$set": {"key": "wholesale_tiers", "value": tiers, "updated_at": datetime.now(timezone.utc).isoformat()}},
        upsert=True
    )
    
    return {"message": "Wholesale tiers updated", "tiers": tiers}

# Delete Discount Code
@api_router.delete("/discount-codes/{code}", dependencies=[Depends(get_current_user)])
async def delete_discount_code(code: str, current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.discount_codes.delete_one({"code": code})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Discount code not found")
    return {"message": "Discount code deleted"}

# Reports
@api_router.get("/reports/sales", dependencies=[Depends(get_current_user)])
async def get_sales_report(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    skip: int = 0,
    limit: int = 100,
    current_user: dict = Depends(get_current_user)
):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    query = {"payment_status": "paid"}
    if start_date:
        query["created_at"] = {"$gte": start_date}
    if end_date:
        query.setdefault("created_at", {})["$lte"] = end_date
    
    # Get aggregated totals
    pipeline = [
        {"$match": query},
        {"$group": {
            "_id": None,
            "total_sales": {"$sum": "$total_amount"},
            "total_orders": {"$sum": 1}
        }}
    ]
    
    aggregated = await db.orders.aggregate(pipeline).to_list(length=1)
    
    # Get paginated orders
    orders = await db.orders.find(query, {"_id": 0}).skip(skip).limit(limit).to_list(length=limit)
    
    return {
        "total_sales": aggregated[0]["total_sales"] if aggregated else 0,
        "total_orders": aggregated[0]["total_orders"] if aggregated else 0,
        "orders": orders,
        "pagination": {"skip": skip, "limit": limit}
    }

@api_router.get("/reports/profits", dependencies=[Depends(get_current_user)])
async def get_profits_report(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    # Use aggregation for better performance
    revenue_pipeline = [
        {"$match": {"payment_status": "paid"}},
        {"$group": {"_id": None, "total_revenue": {"$sum": "$total_amount"}}}
    ]
    
    cost_pipeline = [
        {"$group": {
            "_id": None,
            "total_cost": {"$sum": {"$multiply": ["$entry_price", "$quantity"]}}
        }}
    ]
    
    revenue_result = await db.orders.aggregate(revenue_pipeline).to_list(length=1)
    cost_result = await db.inventory_entries.aggregate(cost_pipeline).to_list(length=1)
    
    total_revenue = revenue_result[0]["total_revenue"] if revenue_result else 0
    total_cost = cost_result[0]["total_cost"] if cost_result else 0
    profit = total_revenue - total_cost
    
    return {
        "total_revenue": total_revenue,
        "total_cost": total_cost,
        "profit": profit,
        "profit_margin": (profit / total_revenue * 100) if total_revenue > 0 else 0
    }

# WhatsApp
@api_router.post("/whatsapp/send-order")
async def send_whatsapp_order(order_id: str = Body(...)):
    order = await db.orders.find_one({"id": order_id}, {"_id": 0})
    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # Build WhatsApp message with complete order details
    message = f"""🛍️ *NUEVO PEDIDO RUNETIC*

📋 *INFORMACIÓN DEL PEDIDO*
• Número de Orden: *{order['order_number']}*
• Fecha: {datetime.now(timezone.utc).strftime('%d/%m/%Y %H:%M')}
• Tipo: {order['customer_type'].upper()}

👤 *DATOS DEL CLIENTE*
• Nombre: {order['shipping_address']['full_name']}
• Documento: {order['shipping_address']['document_type']} {order['shipping_address']['document_id']}
• Teléfono: {order['shipping_address']['phone']}
• Email: {order['shipping_address']['email']}

📍 *DIRECCIÓN DE ENVÍO*
{order['shipping_address']['address']}
{order['shipping_address']['city']}, {order['shipping_address']['department']}

🎽 *PRODUCTOS SOLICITADOS*
"""
    
    for idx, item in enumerate(order["items"], 1):
        message += f"\n{idx}. *{item['product_name']}*"
        message += f"\n   • Versión: {item['version_type'].replace('_', ' ').title()}"
        message += f"\n   • Talla: {item['size']}"
        message += f"\n   • Cantidad: {item['quantity']} unidad(es)"
        
        # Add customization details
        custom = item.get('customization', {})
        if custom.get('estampado') and custom['estampado'] != 'sin_estampado':
            message += f"\n   • Estampado: {custom['estampado'].replace('_', ' ').title()}"
        if custom.get('parches') and custom['parches'] != 'sin_parches':
            message += f"\n   • Parches: Oficiales"
        if custom.get('empaque') == 'premium':
            message += f"\n   • Empaque: Premium"
            
        message += f"\n   • Precio: ${item['total_price']:,.0f} COP\n"
    
    message += f"\n💰 *RESUMEN DE PAGO*"
    message += f"\n• Subtotal: ${order['subtotal']:,.0f} COP"
    
    if order.get('discount_amount', 0) > 0:
        message += f"\n• Descuento: -${order['discount_amount']:,.0f} COP"
        if order.get('discount_code'):
            message += f" (Código: {order['discount_code']})"
    
    if order.get('shipping_cost', 0) > 0:
        message += f"\n• Envío: ${order['shipping_cost']:,.0f} COP"
    
    message += f"\n• *TOTAL: ${order['total_amount']:,.0f} COP*"
    
    message += f"\n\n💳 *MÉTODO DE PAGO*"
    payment_methods = {
        'pse': 'PSE',
        'credit_card': 'Tarjeta de Crédito',
        'bank_transfer': 'Transferencia Bancaria',
        'cash_on_delivery': 'Contra Entrega'
    }
    message += f"\n{payment_methods.get(order['payment_method'], order['payment_method'])}"
    
    message += f"\n\n✅ *CONFIRMACIÓN DE TALLA*"
    message += f"\nEl cliente confirmó haber verificado la tabla de tallas."
    
    message += f"\n\n📞 *SIGUIENTE PASO*"
    message += f"\nPor favor confirmar disponibilidad y proceder con el pedido."
    message += f"\n\n_Pedido generado desde RUNETIC E-Commerce_"
    
    # URL encode the message
    import urllib.parse
    encoded_message = urllib.parse.quote(message)
    whatsapp_url = f"https://wa.me/{WHATSAPP_PHONE}?text={encoded_message}"
    
    await db.orders.update_one({"id": order_id}, {"$set": {"whatsapp_sent": True}})
    
    return {"message": "WhatsApp message prepared", "url": whatsapp_url}

# ==================== WOMPI PAYMENT GATEWAY ====================
import httpx

class WompiPaymentRequest(BaseModel):
    order_id: str
    amount_in_cents: int
    customer_email: str
    customer_name: str
    customer_phone: Optional[str] = None
    customer_document_type: str = "CC"
    customer_document: str
    payment_method: str = "PSE"  # PSE or CARD
    redirect_url: str

class WompiPSERequest(BaseModel):
    order_id: str
    amount_in_cents: int
    customer_email: str
    customer_name: str
    customer_phone: str
    customer_document_type: str
    customer_document: str
    user_type: int = 0  # 0 = persona natural, 1 = persona jurídica
    financial_institution_code: str
    redirect_url: str

@api_router.get("/payments/wompi/config")
async def get_wompi_config():
    """Get WOMPI public configuration"""
    return {
        "public_key": WOMPI_PUBLIC_KEY,
        "currency": "COP",
        "country": "CO",
        "api_url": WOMPI_API_BASE_URL
    }

@api_router.get("/payments/wompi/banks")
async def get_pse_banks():
    """Get list of available PSE banks from WOMPI"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{WOMPI_API_BASE_URL}/pse/financial_institutions",
                headers={"Authorization": f"Bearer {WOMPI_PUBLIC_KEY}"}
            )
            if response.status_code == 200:
                return response.json()
            else:
                logger.error(f"Error fetching banks: {response.text}")
                return {"data": []}
    except Exception as e:
        logger.error(f"Error fetching PSE banks: {str(e)}")
        return {"data": []}

@api_router.get("/payments/wompi/check-pending/{order_id}")
async def check_pending_payment(order_id: str):
    """Check if there's a pending payment for this order - BLOCKS if pending exists"""
    try:
        # Check for any PENDING transaction for this order
        pending = await db.payment_attempts.find_one({
            "order_id": order_id,
            "status": {"$in": ["initiated", "pending", "PENDING"]}
        }, {"_id": 0})
        
        if pending:
            return {
                "has_pending": True,
                "message": "Tu pago está siendo procesado, espera unos minutos.",
                "reference": pending.get("reference"),
                "created_at": pending.get("created_at")
            }
        
        return {"has_pending": False}
    except Exception as e:
        logger.error(f"Error checking pending payment: {str(e)}")
        return {"has_pending": False}

@api_router.post("/payments/wompi/create-transaction")
async def create_wompi_transaction(request: WompiPaymentRequest):
    """
    CRITICAL: Create WOMPI transaction with FRESH acceptance_token
    - Gets NEW acceptance_token from WOMPI API just before creating transaction
    - Token is NOT stored anywhere
    - Each call generates unique reference
    - Blocks if pending transaction exists
    """
    try:
        # STEP 1: Check for pending transactions - BLOCK if exists
        pending = await db.payment_attempts.find_one({
            "order_id": request.order_id,
            "status": {"$in": ["initiated", "pending", "PENDING"]}
        })
        
        if pending:
            raise HTTPException(
                status_code=409,
                detail="Tu pago está siendo procesado, espera unos minutos. No puedes crear otra transacción."
            )
        
        # STEP 2: Get FRESH acceptance_token from WOMPI - DO NOT CACHE
        async with httpx.AsyncClient() as client:
            merchant_response = await client.get(
                f"{WOMPI_API_BASE_URL}/merchants/{WOMPI_PUBLIC_KEY}"
            )
            
            if merchant_response.status_code != 200:
                logger.error(f"Failed to get merchant info: {merchant_response.text}")
                raise HTTPException(
                    status_code=500,
                    detail="Error al obtener configuración del comercio"
                )
            
            merchant_data = merchant_response.json()
            # GET FRESH TOKEN - NOT STORED
            acceptance_token = merchant_data["data"]["presigned_acceptance"]["acceptance_token"]
        
        # STEP 3: Generate UNIQUE reference (timestamp + random)
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        random_part = str(uuid.uuid4()).replace("-", "")[:8].upper()
        unique_reference = f"RUN{timestamp}{random_part}"
        
        # STEP 4: Verify order exists
        order = await db.orders.find_one({"id": request.order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        
        # STEP 5: Register this payment attempt BEFORE calling WOMPI
        attempt_data = {
            "id": str(uuid.uuid4()),
            "order_id": request.order_id,
            "reference": unique_reference,
            "amount_in_cents": request.amount_in_cents,
            "status": "initiated",
            "payment_method": request.payment_method,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_attempts.insert_one(attempt_data)
        
        # STEP 6: Create transaction in WOMPI with FRESH token
        transaction_payload = {
            "acceptance_token": acceptance_token,  # FRESH, NOT CACHED
            "amount_in_cents": request.amount_in_cents,
            "currency": "COP",
            "customer_email": request.customer_email,
            "reference": unique_reference,
            "payment_method": {
                "type": request.payment_method
            },
            "redirect_url": request.redirect_url
        }
        
        # Add customer data
        if request.customer_document:
            transaction_payload["customer_data"] = {
                "phone_number": request.customer_phone,
                "full_name": request.customer_name,
                "legal_id": request.customer_document,
                "legal_id_type": request.customer_document_type
            }
        
        async with httpx.AsyncClient() as client:
            tx_response = await client.post(
                f"{WOMPI_API_BASE_URL}/transactions",
                json=transaction_payload,
                headers={
                    "Authorization": f"Bearer {WOMPI_PUBLIC_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            tx_data = tx_response.json()
            
            if tx_response.status_code not in [200, 201]:
                # Update attempt status to failed
                await db.payment_attempts.update_one(
                    {"reference": unique_reference},
                    {"$set": {"status": "failed", "error": tx_data}}
                )
                logger.error(f"WOMPI transaction failed: {tx_data}")
                raise HTTPException(
                    status_code=400,
                    detail=tx_data.get("error", {}).get("message", "Error al crear transacción en WOMPI")
                )
        
        # STEP 7: Update attempt with WOMPI transaction ID
        wompi_tx_id = tx_data.get("data", {}).get("id")
        wompi_status = tx_data.get("data", {}).get("status")
        
        await db.payment_attempts.update_one(
            {"reference": unique_reference},
            {"$set": {
                "wompi_transaction_id": wompi_tx_id,
                "status": wompi_status,
                "wompi_response": tx_data
            }}
        )
        
        # STEP 8: Update order with payment info
        await db.orders.update_one(
            {"id": request.order_id},
            {"$set": {
                "latest_payment_reference": unique_reference,
                "payment_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"WOMPI transaction created: {unique_reference} -> {wompi_tx_id}")
        
        return {
            "success": True,
            "reference": unique_reference,
            "wompi_transaction_id": wompi_tx_id,
            "status": wompi_status,
            "redirect_url": tx_data.get("data", {}).get("redirect_url"),
            "payment_url": tx_data.get("data", {}).get("payment_url")
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating WOMPI transaction: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error al procesar pago: {str(e)}")

def generate_wompi_signature(reference: str, amount_in_cents: int, currency: str = "COP") -> str:
    """
    Generate WOMPI integrity signature using SHA256
    SECURITY: Private key is only accessed server-side from environment variables
    The signature is: SHA256(reference + amount_in_cents + currency + integrity_secret)
    """
    if not WOMPI_PRIVATE_KEY:
        logger.warning("WOMPI_PRIVATE_KEY not configured - signature will be empty")
        return ""
    
    # Concatenate fields in the required order
    data_to_sign = f"{reference}{amount_in_cents}{currency}{WOMPI_PRIVATE_KEY}"
    
    # Generate SHA256 hash
    signature = hashlib.sha256(data_to_sign.encode('utf-8')).hexdigest()
    
    logger.info(f"Generated integrity signature for reference {reference}")
    return signature


@api_router.post("/payments/wompi/create-pse")
async def create_wompi_pse_transaction(request: WompiPSERequest):
    """
    Create PSE-specific transaction - SECURE SERVER-SIDE IMPLEMENTATION
    
    Security Features:
    - Private key NEVER exposed to frontend
    - Integrity signature generated server-side only
    - Fresh acceptance_token for each transaction
    - Unique reference for each attempt
    
    Flow:
    1. Frontend sends order data (amount, customer info, bank selection)
    2. Backend generates signature using private key (from env vars)
    3. Backend creates transaction with WOMPI
    4. Backend returns ONLY the redirect URL to frontend
    """
    try:
        # Validate private key is configured
        if not WOMPI_PRIVATE_KEY:
            logger.error("WOMPI_PRIVATE_KEY not configured - cannot process production payments")
            raise HTTPException(
                status_code=500, 
                detail="Configuración de pagos incompleta. Contacta al administrador."
            )
        
        # STEP 1: Clean up any old failed/cancelled attempts for this order
        await db.payment_attempts.update_many(
            {
                "order_id": request.order_id,
                "status": {"$in": ["initiated", "failed", "DECLINED", "ERROR", "VOIDED"]}
            },
            {"$set": {"status": "cancelled_for_retry"}}
        )
        
        # STEP 2: Check ONLY for truly pending transactions (in-progress at bank)
        pending = await db.payment_attempts.find_one({
            "order_id": request.order_id,
            "status": {"$in": ["PENDING"]}
        })
        
        if pending:
            created_at = pending.get("created_at")
            if created_at:
                try:
                    created_time = datetime.fromisoformat(created_at.replace('Z', '+00:00'))
                    if datetime.now(timezone.utc) - created_time > timedelta(minutes=15):
                        await db.payment_attempts.update_one(
                            {"id": pending["id"]},
                            {"$set": {"status": "expired"}}
                        )
                    else:
                        raise HTTPException(
                            status_code=409,
                            detail="Tu pago está siendo procesado en el banco. Espera unos minutos antes de reintentar."
                        )
                except ValueError:
                    pass
        
        # STEP 3: Get FRESH acceptance_token from WOMPI API
        logger.info(f"Getting fresh acceptance token from WOMPI for order {request.order_id}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            merchant_response = await client.get(
                f"{WOMPI_API_BASE_URL}/merchants/{WOMPI_PUBLIC_KEY}"
            )
            
            if merchant_response.status_code != 200:
                logger.error(f"Failed to get merchant info: {merchant_response.status_code}")
                raise HTTPException(status_code=500, detail="Error al obtener configuración de WOMPI")
            
            merchant_data = merchant_response.json()
            acceptance_token = merchant_data["data"]["presigned_acceptance"]["acceptance_token"]
            logger.info(f"Got fresh acceptance_token")
        
        # STEP 4: Generate UNIQUE reference for THIS attempt
        timestamp = int(datetime.now(timezone.utc).timestamp() * 1000)
        random_part = str(uuid.uuid4()).replace("-", "")[:8].upper()
        unique_reference = f"RUN{timestamp}{random_part}"
        
        logger.info(f"Generated unique reference: {unique_reference}")
        
        # STEP 5: Verify order exists
        order = await db.orders.find_one({"id": request.order_id}, {"_id": 0})
        if not order:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        
        # STEP 6: Generate INTEGRITY SIGNATURE (server-side only, private key never exposed)
        integrity_signature = generate_wompi_signature(
            reference=unique_reference,
            amount_in_cents=request.amount_in_cents,
            currency="COP"
        )
        
        # STEP 7: Register payment attempt
        attempt_data = {
            "id": str(uuid.uuid4()),
            "order_id": request.order_id,
            "reference": unique_reference,
            "amount_in_cents": request.amount_in_cents,
            "status": "initiated",
            "payment_method": "PSE",
            "bank_code": request.financial_institution_code,
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_attempts.insert_one(attempt_data)
        
        # STEP 8: Create transaction with WOMPI including integrity signature
        transaction_payload = {
            "acceptance_token": acceptance_token,
            "amount_in_cents": request.amount_in_cents,
            "currency": "COP",
            "signature": integrity_signature,  # CRITICAL: Server-generated signature
            "customer_email": request.customer_email,
            "reference": unique_reference,
            "payment_method": {
                "type": "PSE",
                "user_type": request.user_type,
                "user_legal_id_type": request.customer_document_type,
                "user_legal_id": request.customer_document,
                "financial_institution_code": request.financial_institution_code,
                "payment_description": f"Compra RUNETIC #{unique_reference[-8:]}"
            },
            "redirect_url": request.redirect_url,
            "customer_data": {
                "phone_number": request.customer_phone,
                "full_name": request.customer_name,
                "legal_id": request.customer_document,
                "legal_id_type": request.customer_document_type
            }
        }
        
        logger.info(f"Creating PSE transaction with WOMPI: {unique_reference}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            tx_response = await client.post(
                f"{WOMPI_API_BASE_URL}/transactions",
                json=transaction_payload,
                headers={
                    "Authorization": f"Bearer {WOMPI_PUBLIC_KEY}",
                    "Content-Type": "application/json"
                }
            )
            
            tx_data = tx_response.json()
            logger.info(f"WOMPI response status: {tx_response.status_code}")
            
            if tx_response.status_code not in [200, 201]:
                error_msg = tx_data.get("error", {}).get("message", "Error desconocido")
                error_messages = tx_data.get("error", {}).get("messages", {})
                
                await db.payment_attempts.update_one(
                    {"reference": unique_reference},
                    {"$set": {"status": "failed", "error": tx_data}}
                )
                
                logger.error(f"WOMPI PSE transaction failed: {tx_data}")
                
                # Handle specific errors
                if "signature" in str(error_messages).lower():
                    raise HTTPException(status_code=500, detail="Error de configuración de pagos. Contacta soporte.")
                elif "acceptance_token" in str(error_msg).lower():
                    raise HTTPException(status_code=400, detail="Error de autenticación. Por favor intenta de nuevo.")
                else:
                    raise HTTPException(status_code=400, detail=f"Error al procesar pago PSE: {error_msg}")
        
        # STEP 9: Update records with successful response
        wompi_tx_id = tx_data.get("data", {}).get("id")
        wompi_status = tx_data.get("data", {}).get("status")
        pse_redirect_url = tx_data.get("data", {}).get("redirect_url")
        
        await db.payment_attempts.update_one(
            {"reference": unique_reference},
            {"$set": {
                "wompi_transaction_id": wompi_tx_id,
                "status": wompi_status,
                "wompi_response": tx_data
            }}
        )
        
        await db.orders.update_one(
            {"id": request.order_id},
            {"$set": {
                "latest_payment_reference": unique_reference,
                "wompi_transaction_id": wompi_tx_id,
                "payment_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        logger.info(f"PSE transaction created successfully: {unique_reference} -> {wompi_tx_id}")
        
        # SECURITY: Only return redirect URL - no sensitive data exposed
        return {
            "success": True,
            "reference": unique_reference,
            "wompi_transaction_id": wompi_tx_id,
            "redirect_url": pse_redirect_url,
            "status": wompi_status
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating PSE transaction: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Error al procesar pago: {str(e)}")

@api_router.post("/payments/wompi/mark-completed/{reference}")
async def mark_payment_completed(reference: str, status: str = Body(..., embed=True)):
    """Mark a payment attempt as completed (used when user returns from bank)"""
    try:
        await db.payment_attempts.update_one(
            {"reference": reference},
            {"$set": {
                "status": status,
                "completed_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        return {"success": True}
    except Exception as e:
        logger.error(f"Error marking payment completed: {str(e)}")
        return {"success": False}

@api_router.post("/payments/wompi/webhook")
async def wompi_webhook(payload: Dict[str, Any]):
    """Handle WOMPI webhook callbacks for payment status updates"""
    try:
        # Extract transaction data
        event = payload.get("event")
        data = payload.get("data", {}).get("transaction", {})
        
        reference = data.get("reference")
        status = data.get("status")
        wompi_transaction_id = data.get("id")
        
        if not reference:
            return {"success": False, "message": "Missing reference"}
        
        # Map WOMPI status to our status
        status_mapping = {
            "APPROVED": "paid",
            "DECLINED": "failed",
            "ERROR": "failed",
            "VOIDED": "cancelled",
            "PENDING": "pending"
        }
        
        app_status = status_mapping.get(status, "pending")
        
        # Update payment transaction
        await db.payment_transactions.update_one(
            {"reference": reference},
            {"$set": {
                "status": app_status,
                "wompi_transaction_id": wompi_transaction_id,
                "wompi_status": status,
                "updated_at": datetime.now(timezone.utc).isoformat()
            }}
        )
        
        # Update order status
        if app_status == "paid":
            await db.orders.update_one(
                {"payment_reference": reference},
                {"$set": {
                    "payment_status": "paid",
                    "order_status": "confirmed",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        elif app_status == "failed":
            await db.orders.update_one(
                {"payment_reference": reference},
                {"$set": {
                    "payment_status": "failed",
                    "updated_at": datetime.now(timezone.utc).isoformat()
                }}
            )
        
        logger.info(f"WOMPI webhook processed: {reference} -> {status}")
        return {"success": True, "status": app_status}
        
    except Exception as e:
        logger.error(f"WOMPI webhook error: {str(e)}")
        return {"success": False, "message": str(e)}

@api_router.get("/payments/{payment_reference}/status")
async def get_payment_status(payment_reference: str):
    """Get payment status by reference"""
    payment = await db.payment_transactions.find_one(
        {"reference": payment_reference},
        {"_id": 0}
    )
    
    if not payment:
        raise HTTPException(status_code=404, detail="Payment not found")
    
    return payment

# Register a new payment attempt (creates unique entry for each attempt)
class PaymentAttemptRequest(BaseModel):
    order_id: str
    reference: str
    amount_in_cents: int
    session_id: Optional[str] = None

@api_router.post("/payments/wompi/register-attempt")
async def register_payment_attempt(request: PaymentAttemptRequest):
    """Register a new payment attempt - each PSE payment MUST have a unique reference"""
    try:
        # Check if this reference already exists
        existing = await db.payment_attempts.find_one({"reference": request.reference})
        if existing:
            raise HTTPException(
                status_code=400, 
                detail="Esta referencia de pago ya fue utilizada. Por favor inicie un nuevo pago."
            )
        
        # Create new payment attempt record
        attempt_data = {
            "id": str(uuid.uuid4()),
            "order_id": request.order_id,
            "reference": request.reference,
            "amount_in_cents": request.amount_in_cents,
            "session_id": request.session_id,
            "status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        
        await db.payment_attempts.insert_one(attempt_data)
        
        # Update order with latest payment reference
        await db.orders.update_one(
            {"id": request.order_id},
            {"$set": {
                "latest_payment_reference": request.reference,
                "payment_status": "pending",
                "updated_at": datetime.now(timezone.utc).isoformat()
            },
            "$push": {
                "payment_attempts": {
                    "reference": request.reference,
                    "status": "initiated",
                    "created_at": datetime.now(timezone.utc).isoformat()
                }
            }}
        )
        
        logger.info(f"Payment attempt registered: {request.reference} for order {request.order_id}")
        return {"success": True, "reference": request.reference}
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error registering payment attempt: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@api_router.get("/payments/verify/{reference}")
async def verify_payment_status(reference: str):
    """Verify payment status - checks local DB and can be extended to check WOMPI API"""
    try:
        # Check local payment attempt
        attempt = await db.payment_attempts.find_one(
            {"reference": reference},
            {"_id": 0}
        )
        
        if attempt:
            return {
                "reference": reference,
                "status": attempt.get("status", "PENDING").upper(),
                "created_at": attempt.get("created_at")
            }
        
        # Check payment transactions (legacy)
        transaction = await db.payment_transactions.find_one(
            {"reference": reference},
            {"_id": 0}
        )
        
        if transaction:
            status_map = {
                "pending": "PENDING",
                "paid": "APPROVED",
                "failed": "DECLINED",
                "cancelled": "CANCELLED"
            }
            return {
                "reference": reference,
                "status": status_map.get(transaction.get("status", "pending"), "PENDING"),
                "created_at": transaction.get("created_at")
            }
        
        return {"reference": reference, "status": "PENDING"}
        
    except Exception as e:
        logger.error(f"Error verifying payment: {str(e)}")
        return {"reference": reference, "status": "PENDING", "error": str(e)}

# ==================== BANNER MANAGEMENT ====================

class BannerCreate(BaseModel):
    image_url: str
    title: Optional[str] = None
    link: Optional[str] = None
    order: int = 0
    active: bool = True

@api_router.get("/banners")
async def get_banners(active_only: bool = True):
    """Get all banners for carousel display"""
    query = {"active": True} if active_only else {}
    banners = await db.banners.find(query, {"_id": 0}).sort("order", 1).to_list(length=20)
    return {"banners": banners}

@api_router.get("/banners/admin", dependencies=[Depends(get_current_user)])
async def get_all_banners(current_user: dict = Depends(get_current_user)):
    """Get all banners for admin management"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    banners = await db.banners.find({}, {"_id": 0}).sort("order", 1).to_list(length=50)
    return {"banners": banners}

@api_router.post("/banners", dependencies=[Depends(get_current_user)])
async def create_banner(banner: BannerCreate, current_user: dict = Depends(get_current_user)):
    """Create a new banner"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    banner_data = {
        "id": str(uuid.uuid4()),
        "image_url": banner.image_url,
        "title": banner.title,
        "link": banner.link,
        "order": banner.order,
        "active": banner.active,
        "created_at": datetime.now(timezone.utc).isoformat()
    }
    
    await db.banners.insert_one(banner_data)
    return {"message": "Banner created", "id": banner_data["id"]}

@api_router.put("/banners/{banner_id}", dependencies=[Depends(get_current_user)])
async def update_banner(banner_id: str, data: Dict[str, Any], current_user: dict = Depends(get_current_user)):
    """Update a banner"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    result = await db.banners.update_one({"id": banner_id}, {"$set": data})
    
    if result.modified_count == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    
    return {"message": "Banner updated"}

@api_router.delete("/banners/{banner_id}", dependencies=[Depends(get_current_user)])
async def delete_banner(banner_id: str, current_user: dict = Depends(get_current_user)):
    """Delete a banner"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    result = await db.banners.delete_one({"id": banner_id})
    
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Banner not found")
    
    return {"message": "Banner deleted"}

@api_router.put("/banners/reorder", dependencies=[Depends(get_current_user)])
async def reorder_banners(data: Dict[str, List[str]], current_user: dict = Depends(get_current_user)):
    """Reorder banners by updating their order field"""
    if current_user.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    
    banner_ids = data.get("banner_ids", [])
    
    from pymongo import UpdateOne
    operations = [
        UpdateOne({"id": banner_id}, {"$set": {"order": index}})
        for index, banner_id in enumerate(banner_ids)
    ]
    
    if operations:
        await db.banners.bulk_write(operations)
    
    return {"message": "Banners reordered"}

# ==================== WOMPI CARD WIDGET SIGNATURE ====================

class CardWidgetSignatureRequest(BaseModel):
    order_id: str
    amount_in_cents: int
    reference: str

@api_router.post("/payments/wompi/card-widget-signature")
async def get_card_widget_signature(request: CardWidgetSignatureRequest):
    """
    Generate integrity signature for WOMPI Card Widget
    This endpoint allows secure card payments through WOMPI's hosted checkout.
    The signature is generated server-side to keep the private key secure.
    """
    try:
        # Verify order exists
        order = await db.orders.find_one({"id": request.order_id}, {"_id": 0, "id": 1})
        if not order:
            raise HTTPException(status_code=404, detail="Orden no encontrada")
        
        # Check if WOMPI private key is configured
        if not WOMPI_PRIVATE_KEY:
            logger.warning("WOMPI_PRIVATE_KEY not configured - card payments may fail")
            # Return without signature for sandbox mode
            return {
                "success": True,
                "signature": "",
                "public_key": WOMPI_PUBLIC_KEY,
                "warning": "Signature not available - sandbox mode"
            }
        
        # Generate integrity signature
        # Format: SHA256(reference + amount_in_cents + currency + integrity_secret)
        currency = "COP"
        data_to_sign = f"{request.reference}{request.amount_in_cents}{currency}{WOMPI_PRIVATE_KEY}"
        signature = hashlib.sha256(data_to_sign.encode('utf-8')).hexdigest()
        
        # Log the payment attempt
        attempt_data = {
            "id": str(uuid.uuid4()),
            "order_id": request.order_id,
            "reference": request.reference,
            "amount_in_cents": request.amount_in_cents,
            "payment_method": "CARD_WIDGET",
            "status": "initiated",
            "created_at": datetime.now(timezone.utc).isoformat()
        }
        await db.payment_attempts.insert_one(attempt_data)
        
        logger.info(f"Card widget signature generated for order {request.order_id}, reference {request.reference}")
        
        return {
            "success": True,
            "signature": signature,
            "public_key": WOMPI_PUBLIC_KEY,
            "reference": request.reference
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating card widget signature: {str(e)}")
        raise HTTPException(status_code=500, detail="Error al generar firma de pago")

app.include_router(api_router)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@app.on_event("shutdown")
async def shutdown_db_client():
    client.close()