"""
RUNETIC E-Commerce API Tests
Tests for: Auth, Products, Orders, WOMPI Payment, Inventory
"""
import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_USERNAME = "Runetic.col"
ADMIN_PASSWORD = "1022378240RUNETICSA"
MAYORISTA_USERNAME = "RuneticMayorista"
MAYORISTA_PASSWORD = "RuneticM102"


class TestAuth:
    """Authentication endpoint tests"""
    
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "access_token" in data, "Missing access_token in response"
        assert data["role"] == "admin", f"Expected role 'admin', got '{data.get('role')}'"
        assert data["token_type"] == "bearer"
    
    def test_mayorista_login_success(self):
        """Test mayorista login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": MAYORISTA_USERNAME,
            "password": MAYORISTA_PASSWORD
        })
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "mayorista"
    
    def test_login_invalid_credentials(self):
        """Test login with invalid credentials returns 401"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "invalid_user",
            "password": "wrong_password"
        })
        assert response.status_code == 401, f"Expected 401, got {response.status_code}"


class TestProducts:
    """Products API tests"""
    
    def test_get_products_returns_list(self):
        """Test GET /api/products returns product list"""
        response = requests.get(f"{BASE_URL}/api/products?limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data, "Missing 'products' key in response"
        assert "total" in data, "Missing 'total' key in response"
        assert isinstance(data["products"], list)
        assert len(data["products"]) > 0, "Products list should not be empty"
    
    def test_get_products_total_count(self):
        """Test that total products count is 254"""
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert response.status_code == 200
        
        data = response.json()
        assert data["total"] == 254, f"Expected 254 products, got {data['total']}"
    
    def test_get_products_with_pagination(self):
        """Test products pagination works"""
        response = requests.get(f"{BASE_URL}/api/products?skip=0&limit=50")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["products"]) == 50, f"Expected 50 products, got {len(data['products'])}"
    
    def test_get_products_by_category(self):
        """Test filtering products by category"""
        response = requests.get(f"{BASE_URL}/api/products?category=futbol&limit=10")
        assert response.status_code == 200
        
        data = response.json()
        assert len(data["products"]) > 0, "Should have futbol products"
        for product in data["products"]:
            assert product["category"] == "futbol"
    
    def test_product_has_valid_prices(self):
        """Test that products have valid (non-NaN) prices"""
        response = requests.get(f"{BASE_URL}/api/products?limit=50")
        assert response.status_code == 200
        
        data = response.json()
        for product in data["products"]:
            retail_price = product.get("base_price_retail")
            wholesale_price = product.get("base_price_wholesale")
            
            # Check prices are valid numbers (not NaN)
            assert retail_price is not None, f"Product {product['code']} has null retail price"
            assert wholesale_price is not None, f"Product {product['code']} has null wholesale price"
            assert isinstance(retail_price, (int, float)), f"Product {product['code']} retail price is not a number"
            assert isinstance(wholesale_price, (int, float)), f"Product {product['code']} wholesale price is not a number"
            # Check for NaN (NaN != NaN)
            assert retail_price == retail_price, f"Product {product['code']} has NaN retail price"
            assert wholesale_price == wholesale_price, f"Product {product['code']} has NaN wholesale price"
    
    def test_get_single_product(self):
        """Test GET /api/products/{id} returns single product"""
        # First get a product ID
        list_response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert list_response.status_code == 200
        
        products = list_response.json()["products"]
        assert len(products) > 0
        
        product_id = products[0]["id"]
        
        # Get single product
        response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert response.status_code == 200
        
        product = response.json()
        assert product["id"] == product_id
        assert "reference" in product
        assert "category" in product
    
    def test_get_nonexistent_product_returns_404(self):
        """Test GET /api/products/{invalid_id} returns 404"""
        response = requests.get(f"{BASE_URL}/api/products/nonexistent-id-12345")
        assert response.status_code == 404


class TestWompiPayment:
    """WOMPI Payment Gateway tests"""
    
    def test_get_wompi_config(self):
        """Test GET /api/payments/wompi/config returns public key"""
        response = requests.get(f"{BASE_URL}/api/payments/wompi/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "public_key" in data, "Missing public_key in WOMPI config"
        assert data["public_key"].startswith("pub_"), f"Invalid public key format: {data['public_key']}"
        assert data["currency"] == "COP"
        assert data["country"] == "CO"


class TestOrders:
    """Orders API tests"""
    
    def test_create_order_success(self):
        """Test POST /api/orders creates order successfully"""
        # Get a product first
        products_response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert products_response.status_code == 200
        product = products_response.json()["products"][0]
        
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": product["id"],
                "product_code": product["code"],
                "product_name": product["reference"],
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
                "unit_price": product["base_price_retail"],
                "total_price": product["base_price_retail"]
            }],
            "shipping_address": {
                "full_name": "TEST_User Order",
                "document_type": "CC",
                "document_id": "123456789",
                "phone": "3001234567",
                "email": "test@example.com",
                "address": "Calle Test 123",
                "city": "Bogotá",
                "department": "Cundinamarca"
            },
            "payment_method": "cash_on_delivery",
            "discount_code": None,
            "size_confirmation": True
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order_id" in data, "Missing order_id in response"
        assert "order_number" in data, "Missing order_number in response"
        assert data["order_number"].startswith("ORD-"), f"Invalid order number format: {data['order_number']}"
    
    def test_create_order_missing_fields_fails(self):
        """Test POST /api/orders with missing fields returns error"""
        incomplete_order = {
            "customer_type": "retail",
            "items": []
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=incomplete_order)
        # Should fail due to validation
        assert response.status_code in [400, 422], f"Expected 400/422, got {response.status_code}"


class TestAdminEndpoints:
    """Admin-protected endpoint tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Admin authentication failed")
    
    def test_get_orders_requires_auth(self):
        """Test GET /api/orders requires authentication"""
        response = requests.get(f"{BASE_URL}/api/orders")
        assert response.status_code in [401, 403], f"Expected 401/403, got {response.status_code}"
    
    def test_get_orders_with_auth(self, admin_token):
        """Test GET /api/orders with valid auth token"""
        response = requests.get(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "orders" in data
        assert "total" in data
    
    def test_get_inventory_entries_requires_auth(self):
        """Test GET /api/inventory/entries requires authentication"""
        response = requests.get(f"{BASE_URL}/api/inventory/entries")
        assert response.status_code in [401, 403]
    
    def test_get_inventory_entries_with_auth(self, admin_token):
        """Test GET /api/inventory/entries with valid auth"""
        response = requests.get(
            f"{BASE_URL}/api/inventory/entries",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "entries" in data
        assert "total" in data
    
    def test_get_discount_codes_requires_auth(self):
        """Test GET /api/discount-codes requires authentication"""
        response = requests.get(f"{BASE_URL}/api/discount-codes")
        assert response.status_code in [401, 403]
    
    def test_get_discount_codes_with_auth(self, admin_token):
        """Test GET /api/discount-codes with valid auth"""
        response = requests.get(
            f"{BASE_URL}/api/discount-codes",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "codes" in data
        assert "total" in data


class TestWhatsApp:
    """WhatsApp integration tests"""
    
    def test_send_whatsapp_order_invalid_id(self):
        """Test POST /api/whatsapp/send-order with invalid order ID"""
        response = requests.post(
            f"{BASE_URL}/api/whatsapp/send-order",
            json={"order_id": "nonexistent-order-id"}
        )
        # Returns 404 (not found) or 422 (validation error)
        assert response.status_code in [404, 422]


class TestOrderStatusChange:
    """Order status change API tests - Issue #1 fix verification"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Admin authentication failed")
    
    @pytest.fixture
    def test_order_id(self, admin_token):
        """Get an existing order ID for testing"""
        response = requests.get(
            f"{BASE_URL}/api/orders?limit=1",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        if response.status_code == 200 and response.json()["orders"]:
            return response.json()["orders"][0]["id"]
        pytest.skip("No orders available for testing")
    
    def test_update_order_status_to_paid(self, admin_token, test_order_id):
        """Test PUT /api/orders/{id}/status with 'paid' status"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order_id}/status",
            json={"status": "paid"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["message"] == "Order status updated"
        assert data["status"] == "paid"
    
    def test_update_order_status_to_delivered(self, admin_token, test_order_id):
        """Test PUT /api/orders/{id}/status with 'delivered' status"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order_id}/status",
            json={"status": "delivered"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["message"] == "Order status updated"
        assert data["status"] == "delivered"
        
        # Verify the order was actually updated
        verify_response = requests.get(
            f"{BASE_URL}/api/orders/{test_order_id}",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert verify_response.status_code == 200
        order = verify_response.json()
        assert order["order_status"] == "delivered"
        assert order["payment_status"] == "paid"
    
    def test_update_order_status_to_cancelled(self, admin_token, test_order_id):
        """Test PUT /api/orders/{id}/status with 'cancelled' status"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order_id}/status",
            json={"status": "cancelled"},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["message"] == "Order status updated"
        assert data["status"] == "cancelled"
    
    def test_update_order_status_requires_auth(self, test_order_id):
        """Test PUT /api/orders/{id}/status requires authentication"""
        response = requests.put(
            f"{BASE_URL}/api/orders/{test_order_id}/status",
            json={"status": "paid"}
        )
        assert response.status_code in [401, 403]


class TestWholesaleTiers:
    """Wholesale discount tiers API tests - Issue #4 fix verification"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Admin authentication failed")
    
    def test_get_wholesale_tiers(self, admin_token):
        """Test GET /api/settings/wholesale-tiers returns tiers"""
        response = requests.get(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "tiers" in data, "Missing 'tiers' key in response"
        assert isinstance(data["tiers"], list)
        assert len(data["tiers"]) > 0, "Tiers list should not be empty"
        
        # Verify tier structure
        for tier in data["tiers"]:
            assert "min_quantity" in tier
            assert "discount_percent" in tier
    
    def test_update_wholesale_tiers(self, admin_token):
        """Test PUT /api/settings/wholesale-tiers updates tiers"""
        new_tiers = [
            {"min_quantity": 1, "max_quantity": 9, "discount_percent": 30},
            {"min_quantity": 10, "max_quantity": 19, "discount_percent": 35},
            {"min_quantity": 20, "max_quantity": 49, "discount_percent": 40},
            {"min_quantity": 50, "max_quantity": None, "discount_percent": 45}
        ]
        
        response = requests.put(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            json={"tiers": new_tiers},
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["message"] == "Wholesale tiers updated"
        assert "tiers" in data
        
        # Verify the update persisted
        verify_response = requests.get(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert verify_response.status_code == 200
        verify_data = verify_response.json()
        assert len(verify_data["tiers"]) == 4
    
    def test_wholesale_tiers_requires_auth(self):
        """Test GET /api/settings/wholesale-tiers requires authentication"""
        response = requests.get(f"{BASE_URL}/api/settings/wholesale-tiers")
        assert response.status_code in [401, 403]


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
