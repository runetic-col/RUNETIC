import pandas as pd
import asyncio
from motor.motor_asyncio import AsyncIOMotorClient
import os
from dotenv import load_dotenv
from pathlib import Path
import uuid
from datetime import datetime, timezone

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

# Size charts data
SIZE_CHARTS = {
    "dama": {
        "XS": {"width": "36-38 cm", "length": "58-60 cm"},
        "S": {"width": "38-40 cm", "length": "60-62 cm"},
        "M": {"width": "42-44 cm", "length": "62-64 cm"},
        "L": {"width": "44-46 cm", "length": "64-66 cm"},
        "XL": {"width": "46-47 cm", "length": "66-67 cm"}
    },
    "nino": {
        "6": {"age": "4-5", "width": "37 cm", "length": "47 cm"},
        "8": {"age": "5-6", "width": "39 cm", "length": "50 cm"},
        "10": {"age": "7-8", "width": "41 cm", "length": "53 cm"},
        "12": {"age": "9-10", "width": "43 cm", "length": "56 cm"},
        "14": {"age": "10-11", "width": "45 cm", "length": "59 cm"},
        "16": {"age": "12-14", "width": "47 cm", "length": "62 cm"}
    },
    "hombre_fan": {
        "S": {"width": "49-51 cm", "length": "67-69 cm"},
        "M": {"width": "51-53 cm", "length": "69-71 cm"},
        "L": {"width": "53-55 cm", "length": "71-73 cm"},
        "XL": {"width": "55-57 cm", "length": "73-76 cm"},
        "2XL": {"width": "58-60 cm", "length": "77-79 cm"}
    },
    "hombre_jugador": {
        "S": {"width": "47-49 cm", "length": "65-67 cm"},
        "M": {"width": "49-51 cm", "length": "67-69 cm"},
        "L": {"width": "51-53 cm", "length": "69-71 cm"},
        "XL": {"width": "53-55 cm", "length": "71-73 cm"},
        "2XL": {"width": "53-55 cm", "length": "71-73 cm"}
    }
}

async def import_inventory():
    print("Starting inventory import...")
    
    # Read Excel file
    xl_file = pd.ExcelFile('/app/inventario_runetic.xlsx')
    df = pd.read_excel(xl_file, sheet_name='INVENTARIO')
    
    print(f"Found {len(df)} products in Excel")
    
    # Clear existing products
    await db.products.delete_many({})
    print("Cleared existing products")
    
    # Process each row
    for idx, row in df.iterrows():
        try:
            code = str(row['Código'])
            reference = row['Referencia']
            base_price = float(row['Valor'])
            
            # Determine category and team from reference
            reference_lower = reference.lower()
            category = "futbol"  # Default
            if "nfl" in reference_lower or "patriots" in reference_lower or "cowboys" in reference_lower:
                category = "nfl"
            elif "f1" in reference_lower or "formula" in reference_lower:
                category = "formula1"
            elif "baseball" in reference_lower or "yankees" in reference_lower:
                category = "baseball"
            
            # Extract team name (simplified)
            team = reference.split()[0] if len(reference.split()) > 0 else "Team"
            
            # Get stock data - diferentes tallas según versión
            stock_hombre = {
                "S": int(row.get('Talla S', 0) or 0),
                "M": int(row.get('Talla M', 0) or 0),
                "L": int(row.get('Talla L', 0) or 0),
                "XL": int(row.get('Talla XL', 0) or 0),
                "2XL": int(row.get('Talla 2XL', 0) or 0)
            }
            
            stock_dama = {
                "XS": int(row.get('Talla XS', 0) or 0),
                "S": int(row.get('Talla S', 0) or 0),
                "M": int(row.get('Talla M', 0) or 0),
                "L": int(row.get('Talla L', 0) or 0),
                "XL": int(row.get('Talla XL', 0) or 0)
            }
            
            stock_nino = {
                "6": 5,
                "8": 5,
                "10": 5,
                "12": 5,
                "14": 5,
                "16": 5
            }
            
            stock = {
                "hombre_fan": stock_hombre,
                "hombre_jugador": stock_hombre,
                "dama": stock_dama,
                "nino": stock_nino
            }
            
            # Available sizes según versión
            available_sizes_map = {
                "hombre_fan": ["S", "M", "L", "XL", "2XL"],
                "hombre_jugador": ["S", "M", "L", "XL", "2XL"],
                "dama": ["XS", "S", "M", "L", "XL"],
                "nino": ["6", "8", "10", "12", "14", "16"]
            }
            
            # Create product
            product = {
                "id": str(uuid.uuid4()),
                "code": code,
                "reference": reference,
                "category": category,
                "team": team,
                "base_price_retail": base_price,
                "base_price_wholesale": base_price * 0.7,  # 30% discount for wholesale
                "versions": [
                    {"version_type": "hombre_fan", "base_price": base_price},
                    {"version_type": "hombre_jugador", "base_price": base_price + 10000},
                    {"version_type": "dama", "base_price": base_price},
                    {"version_type": "nino", "base_price": base_price - 10000}
                ],
                "available_sizes": ["S", "M", "L", "XL", "2XL"],  # Default hombre
                "available_sizes_by_version": available_sizes_map,
                "size_charts": [
                    {"version_type": "hombre_fan", "sizes": SIZE_CHARTS["hombre_fan"]},
                    {"version_type": "hombre_jugador", "sizes": SIZE_CHARTS["hombre_jugador"]},
                    {"version_type": "dama", "sizes": SIZE_CHARTS["dama"]},
                    {"version_type": "nino", "sizes": SIZE_CHARTS["nino"]}
                ],
                "images": {
                    "fan": ["https://images.pexels.com/photos/31543207/pexels-photo-31543207.jpeg"],
                    "jugador": ["https://images.pexels.com/photos/31543207/pexels-photo-31543207.jpeg"]
                },
                "stock": stock,
                "active": True,
                "created_at": datetime.now(timezone.utc).isoformat()
            }
            
            await db.products.insert_one(product)
            print(f"Imported: {reference}")
            
        except Exception as e:
            print(f"Error importing row {idx}: {e}")
            continue
    
    print(f"\\nImport completed!")
    
    # Print summary
    total_products = await db.products.count_documents({})
    print(f"Total products in database: {total_products}")

if __name__ == "__main__":
    asyncio.run(import_inventory())
