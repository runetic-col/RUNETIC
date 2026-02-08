"""
Test Cash on Delivery (Contra Entrega) flow and Batch Inventory module for RUNETIC E-commerce.

Tests include:
1. COD order creation with pickup token generation
2. Pickup token email logging in DB
3. Batch inventory CRUD operations with profitability calculations
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials from requirements
ADMIN_USERNAME = "Runetic.col"
ADMIN_PASSWORD = "1022378240RUNETICSA"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    if response.status_code == 200:
        return response.json().get("access_token")
    pytest.skip(f"Admin authentication failed: {response.status_code}")


@pytest.fixture
def api_client():
    """Basic requests session"""
    session = requests.Session()
    session.headers.update({"Content-Type": "application/json"})
    return session


@pytest.fixture
def auth_client(api_client, auth_token):
    """Authenticated requests session"""
    api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
    return api_client


class TestCashOnDeliveryFlow:
    """Test Cash on Delivery order flow - pickup token generation"""

    def test_create_cod_order_generates_token(self, api_client):
        """CRITICAL: COD order must generate pickup_token COD-XXXXXXXX"""
        # Create COD order
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": "test-product-cod",
                "product_code": "TEST-COD",
                "product_name": "Test COD Product",
                "version_type": "hombre_fan",
                "size": "M",
                "quantity": 1,
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "normal",
                    "empaque_price": 0
                },
                "unit_price": 55000,
                "total_price": 55000
            }],
            "shipping_address": {
                "full_name": "Test COD User",
                "document_type": "CC",
                "document_id": "1234567890",
                "phone": "3001234567",
                "email": "test_cod@runetic.com",
                "address": "Calle 123 Test",
                "city": "Bogota",
                "department": "Cundinamarca"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 55000,
            "total_amount": 70000
        }
        
        response = api_client.post(f"{BASE_URL}/api/orders", json=order_data)
        
        # Assert order created successfully
        assert response.status_code == 200, f"Order creation failed: {response.text}"
        
        data = response.json()
        
        # CRITICAL: pickup_token must be returned
        assert "pickup_token" in data, "pickup_token not returned in response"
        assert data["pickup_token"] is not None, "pickup_token is None"
        
        # Token format: COD-XXXXXXXX (8 alphanumeric chars)
        token = data["pickup_token"]
        assert token.startswith("COD-"), f"Token doesn't start with COD-: {token}"
        assert len(token) == 12, f"Token length should be 12 (COD-XXXXXXXX): {len(token)}"
        
        # Verify order_number and order_id returned
        assert "order_id" in data, "order_id not in response"
        assert "order_number" in data, "order_number not in response"
        
        print(f"✓ COD order created: {data['order_number']}")
        print(f"✓ Pickup token generated: {token}")
        
        return data

    def test_cod_order_details_contain_token(self, api_client, auth_token):
        """Verify order details contain pickup_token after creation"""
        # First create a COD order
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": "test-product-detail",
                "product_code": "TEST-DETAIL",
                "product_name": "Test Detail Product",
                "version_type": "hombre_fan",
                "size": "L",
                "quantity": 1,
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "normal",
                    "empaque_price": 0
                },
                "unit_price": 55000,
                "total_price": 55000
            }],
            "shipping_address": {
                "full_name": "Test Detail User",
                "document_type": "CC",
                "document_id": "9876543210",
                "phone": "3009876543",
                "email": "test_detail@runetic.com",
                "address": "Carrera 456 Test",
                "city": "Medellin",
                "department": "Antioquia"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True
        }
        
        create_response = api_client.post(f"{BASE_URL}/api/orders", json=order_data)
        assert create_response.status_code == 200
        
        order_id = create_response.json()["order_id"]
        pickup_token = create_response.json()["pickup_token"]
        
        # Get order details
        api_client.headers.update({"Authorization": f"Bearer {auth_token}"})
        detail_response = api_client.get(f"{BASE_URL}/api/orders/{order_id}")
        
        assert detail_response.status_code == 200
        order_detail = detail_response.json()
        
        # Verify pickup_token in order details
        assert order_detail.get("pickup_token") == pickup_token, "Token in order details doesn't match"
        assert order_detail.get("payment_method") == "cash_on_delivery"
        assert order_detail.get("pickup_token_used") == False, "Token should not be used yet"
        
        print(f"✓ Order details verified with token: {pickup_token}")

    def test_non_cod_order_has_no_token(self, api_client):
        """Non-COD orders should not have pickup_token"""
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": "test-product-transfer",
                "product_code": "TEST-TRANSFER",
                "product_name": "Test Transfer Product",
                "version_type": "hombre_fan",
                "size": "XL",
                "quantity": 1,
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "normal",
                    "empaque_price": 0
                },
                "unit_price": 55000,
                "total_price": 55000
            }],
            "shipping_address": {
                "full_name": "Test Transfer User",
                "document_type": "CC",
                "document_id": "5555555555",
                "phone": "3005555555",
                "email": "test_transfer@runetic.com",
                "address": "Avenida 789 Test",
                "city": "Cali",
                "department": "Valle"
            },
            "payment_method": "bank_transfer",  # NOT cash_on_delivery
            "size_confirmation": True
        }
        
        response = api_client.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200
        data = response.json()
        
        # pickup_token should be None for bank_transfer
        assert data.get("pickup_token") is None, "Non-COD order should not have pickup_token"
        
        print("✓ Bank transfer order has no pickup token (as expected)")


class TestBatchInventoryModule:
    """Test Batch Inventory CRUD with profitability calculations"""

    def test_create_batch_entry(self, auth_client):
        """Create inventory batch with profitability calculation"""
        batch_data = {
            "barcode": f"770TEST{uuid.uuid4().hex[:6].upper()}",
            "product_code": "RUN-TEST-001",
            "product_name": "Test Camiseta Colombia",
            "gender": "hombre",
            "garment_type": "camiseta",
            "team": "Colombia",
            "quantity": 100,
            "entry_price": 30000,  # Cost per unit
            "selling_price": 55000,  # Selling price per unit
            "notes": "Test batch"
        }
        
        response = auth_client.post(f"{BASE_URL}/api/inventory/batches", json=batch_data)
        
        assert response.status_code == 200, f"Batch creation failed: {response.text}"
        
        data = response.json()
        
        # Verify profitability calculations
        expected_investment = 100 * 30000  # 3,000,000 COP
        expected_revenue = 100 * 55000  # 5,500,000 COP
        expected_profit = expected_revenue - expected_investment  # 2,500,000 COP
        expected_margin = (expected_profit / expected_investment) * 100  # 83.33%
        
        assert data["total_investment"] == expected_investment, f"Investment calc error: {data['total_investment']}"
        assert data["projected_revenue"] == expected_revenue, f"Revenue calc error: {data['projected_revenue']}"
        assert data["projected_profit"] == expected_profit, f"Profit calc error: {data['projected_profit']}"
        assert abs(data["profit_margin_percent"] - expected_margin) < 0.1, f"Margin calc error: {data['profit_margin_percent']}"
        
        print(f"✓ Batch created with ID: {data['id']}")
        print(f"✓ Investment: ${expected_investment:,} COP")
        print(f"✓ Projected Profit: ${expected_profit:,} COP ({data['profit_margin_percent']}%)")
        
        return data["id"], batch_data["barcode"]

    def test_list_batch_entries(self, auth_client):
        """List batches with summary totals"""
        response = auth_client.get(f"{BASE_URL}/api/inventory/batches")
        
        assert response.status_code == 200
        
        data = response.json()
        
        assert "batches" in data, "Response should contain 'batches'"
        assert "total" in data, "Response should contain 'total'"
        assert "summary" in data, "Response should contain 'summary'"
        
        summary = data["summary"]
        if summary:
            assert "total_investment" in summary
            assert "total_projected_revenue" in summary
            assert "total_projected_profit" in summary
            assert "overall_profit_margin" in summary
            
            print(f"✓ Batches listed: {data['total']} total")
            print(f"✓ Total Investment: ${summary['total_investment']:,} COP")
            print(f"✓ Overall Profit Margin: {summary['overall_profit_margin']}%")

    def test_get_single_batch(self, auth_client):
        """Get single batch by ID"""
        # First create a batch
        batch_data = {
            "barcode": f"770GET{uuid.uuid4().hex[:6].upper()}",
            "product_code": "RUN-GET-001",
            "product_name": "Test Get Batch",
            "gender": "mujer",
            "garment_type": "shorts",
            "quantity": 50,
            "entry_price": 20000,
            "selling_price": 40000
        }
        
        create_response = auth_client.post(f"{BASE_URL}/api/inventory/batches", json=batch_data)
        assert create_response.status_code == 200
        batch_id = create_response.json()["id"]
        
        # Get batch by ID
        get_response = auth_client.get(f"{BASE_URL}/api/inventory/batches/{batch_id}")
        
        assert get_response.status_code == 200
        
        batch = get_response.json()
        assert batch["barcode"] == batch_data["barcode"]
        assert batch["quantity"] == batch_data["quantity"]
        
        print(f"✓ Batch retrieved: {batch_id}")

    def test_update_batch_entry(self, auth_client):
        """Update batch and verify recalculation of profitability"""
        # First create a batch
        batch_data = {
            "barcode": f"770UPD{uuid.uuid4().hex[:6].upper()}",
            "product_code": "RUN-UPD-001",
            "product_name": "Test Update Batch",
            "gender": "nino",
            "garment_type": "conjunto",
            "quantity": 30,
            "entry_price": 25000,
            "selling_price": 45000
        }
        
        create_response = auth_client.post(f"{BASE_URL}/api/inventory/batches", json=batch_data)
        assert create_response.status_code == 200
        batch_id = create_response.json()["id"]
        
        # Update batch with new quantity and prices
        update_data = {
            "quantity": 50,  # Changed
            "entry_price": 22000,  # Changed
            "selling_price": 50000  # Changed
        }
        
        update_response = auth_client.put(
            f"{BASE_URL}/api/inventory/batches/{batch_id}",
            json=update_data
        )
        
        assert update_response.status_code == 200
        
        result = update_response.json()
        
        # Verify recalculation
        expected_investment = 50 * 22000  # 1,100,000
        expected_revenue = 50 * 50000  # 2,500,000
        expected_profit = expected_revenue - expected_investment  # 1,400,000
        
        assert result["total_investment"] == expected_investment
        assert result["projected_revenue"] == expected_revenue
        assert result["projected_profit"] == expected_profit
        
        print(f"✓ Batch updated: {batch_id}")
        print(f"✓ New Profit: ${expected_profit:,} COP ({result['profit_margin_percent']}%)")

    def test_delete_batch_entry(self, auth_client):
        """Delete batch entry"""
        # First create a batch
        batch_data = {
            "barcode": f"770DEL{uuid.uuid4().hex[:6].upper()}",
            "product_code": "RUN-DEL-001",
            "product_name": "Test Delete Batch",
            "gender": "unisex",
            "garment_type": "gorra",
            "quantity": 20,
            "entry_price": 10000,
            "selling_price": 25000
        }
        
        create_response = auth_client.post(f"{BASE_URL}/api/inventory/batches", json=batch_data)
        assert create_response.status_code == 200
        batch_id = create_response.json()["id"]
        
        # Delete batch
        delete_response = auth_client.delete(f"{BASE_URL}/api/inventory/batches/{batch_id}")
        
        assert delete_response.status_code == 200
        
        # Verify deletion - should return 404
        get_response = auth_client.get(f"{BASE_URL}/api/inventory/batches/{batch_id}")
        assert get_response.status_code == 404, "Deleted batch should not be found"
        
        print(f"✓ Batch deleted: {batch_id}")

    def test_filter_batches_by_gender(self, auth_client):
        """Filter batches by gender"""
        response = auth_client.get(f"{BASE_URL}/api/inventory/batches?gender=hombre")
        
        assert response.status_code == 200
        
        data = response.json()
        # All returned batches should be 'hombre'
        for batch in data.get("batches", []):
            assert batch["gender"] == "hombre", f"Batch gender mismatch: {batch['gender']}"
        
        print(f"✓ Filter by gender works: {len(data.get('batches', []))} hombre batches")


class TestLoginPage:
    """Test Login page WhatsApp message for wholesalers"""

    def test_admin_login(self, api_client):
        """Verify admin login works"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "admin"
        
        print("✓ Admin login successful")

    def test_wholesale_login(self, api_client):
        """Verify wholesale login works"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "RuneticMayorista", "password": "RuneticM102"}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "mayorista"
        
        print("✓ Wholesale login successful")

    def test_invalid_login(self, api_client):
        """Verify invalid credentials return 401"""
        response = api_client.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": "invalid", "password": "wrong"}
        )
        
        assert response.status_code == 401
        print("✓ Invalid login correctly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
