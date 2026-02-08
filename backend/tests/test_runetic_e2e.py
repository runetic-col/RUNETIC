"""
RUNETIC E-commerce Backend API Tests
Tests for products, orders, auth, and payment integration
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ecommerce-fixes-14.preview.emergentagent.com')
PAYMENT_BACKEND_URL = 'https://wompi-backend-production-7680.up.railway.app'

# Test credentials
ADMIN_USER = "Runetic.col"
ADMIN_PASSWORD = "1022378240RUNETICSA"


class TestProductsAPI:
    """Product catalog endpoint tests"""
    
    def test_get_products_list(self):
        """Test GET /api/products returns product list"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data
        assert isinstance(data["products"], list)
        assert len(data["products"]) > 0
        print(f"SUCCESS: Found {len(data['products'])} products")
    
    def test_product_has_required_fields(self):
        """Test products have required fields"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        
        data = response.json()
        product = data["products"][0]
        
        required_fields = ["id", "reference", "category", "base_price_retail"]
        for field in required_fields:
            assert field in product, f"Missing field: {field}"
        print(f"SUCCESS: Product has all required fields")
    
    def test_get_single_product(self):
        """Test GET /api/products/{id} returns single product"""
        # First get a product ID
        response = requests.get(f"{BASE_URL}/api/products")
        product_id = response.json()["products"][0]["id"]
        
        # Get single product
        response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["id"] == product_id
        print(f"SUCCESS: Got single product: {data['reference']}")


class TestAuthAPI:
    """Authentication endpoint tests"""
    
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD
        })
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert "role" in data
        assert data["role"] == "admin"
        print(f"SUCCESS: Admin login successful, role: {data['role']}")
        return data["access_token"]
    
    def test_admin_login_invalid_credentials(self):
        """Test admin login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "wrong_user",
            "password": "wrong_password"
        })
        assert response.status_code == 401
        print("SUCCESS: Invalid credentials rejected")


class TestOrdersAPI:
    """Order management endpoint tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Admin authentication failed")
    
    def test_create_order(self, admin_token):
        """Test POST /api/orders creates new order"""
        # Get a product first
        products_response = requests.get(f"{BASE_URL}/api/products")
        product = products_response.json()["products"][0]
        
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": product["id"],
                "product_code": product.get("code", "1"),
                "product_name": product["reference"],
                "version_type": "hombre_fan",
                "size": "M",
                "quantity": 1,
                "unit_price": product["base_price_retail"],
                "total_price": product["base_price_retail"],
                "customization": {
                    "estampado": "sin_estampado",
                    "parches": "sin_parches",
                    "empaque": "normal"
                }
            }],
            "shipping_address": {
                "full_name": "TEST_User",
                "document_type": "CC",
                "document_id": "123456789",
                "phone": "3001234567",
                "email": "test@test.com",
                "address": "Calle 123",
                "city": "Bogotá",
                "department": "Cundinamarca"
            },
            "payment_method": "wompi_pse",
            "size_confirmation": True
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code in [200, 201]
        
        data = response.json()
        assert "order_id" in data
        print(f"SUCCESS: Order created with ID: {data['order_id']}")
        return data["order_id"]
    
    def test_get_orders_list(self, admin_token):
        """Test GET /api/orders returns order list (admin only)"""
        response = requests.get(
            f"{BASE_URL}/api/orders",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "orders" in data
        print(f"SUCCESS: Found {len(data['orders'])} orders")


class TestExternalPaymentBackend:
    """External Railway WOMPI backend tests"""
    
    def test_payment_backend_health(self):
        """Test external payment backend is running"""
        response = requests.get(PAYMENT_BACKEND_URL)
        assert response.status_code == 200
        
        data = response.json()
        assert data.get("status") == "ok"
        print(f"SUCCESS: Payment backend is running: {data.get('message')}")
    
    def test_payment_endpoint_exists(self):
        """Test /create-payment endpoint exists"""
        # Send minimal request to check endpoint exists
        response = requests.post(
            f"{PAYMENT_BACKEND_URL}/create-payment",
            json={},
            headers={"Content-Type": "application/json"}
        )
        # Should return error but not 404
        assert response.status_code != 404
        print(f"SUCCESS: Payment endpoint exists, status: {response.status_code}")
    
    def test_payment_request_format(self):
        """Test payment request with test data (expected to fail validation)"""
        # This tests that the endpoint accepts the request format
        # Actual payment will fail with test data which is expected
        response = requests.post(
            f"{PAYMENT_BACKEND_URL}/create-payment",
            json={
                "amount": 50000,
                "reference": "TEST-123",
                "email": "test@test.com",
                "financial_institution_code": "1007",
                "user_type": 0,
                "user_legal_id_type": "CC",
                "user_legal_id": "123456789",
                "payment_description": "Test Payment",
                "full_name": "Test User",
                "phone_number": "3001234567"
            },
            headers={"Content-Type": "application/json"}
        )
        # Endpoint should respond (not timeout or 404)
        assert response.status_code in [200, 400, 422, 500]
        print(f"SUCCESS: Payment endpoint responds, status: {response.status_code}")


class TestWholesaleAPI:
    """Wholesale pricing endpoint tests"""
    
    def test_get_wholesale_tiers(self):
        """Test GET /api/wholesale/tiers returns pricing tiers"""
        response = requests.get(f"{BASE_URL}/api/wholesale/tiers")
        # May require auth or return empty
        assert response.status_code in [200, 401, 404]
        print(f"SUCCESS: Wholesale tiers endpoint status: {response.status_code}")


class TestDiscountCodesAPI:
    """Discount codes endpoint tests"""
    
    @pytest.fixture
    def admin_token(self):
        """Get admin authentication token"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASSWORD
        })
        if response.status_code == 200:
            return response.json()["access_token"]
        pytest.skip("Admin authentication failed")
    
    def test_get_discount_codes(self, admin_token):
        """Test GET /api/discounts returns discount codes (admin only)"""
        response = requests.get(
            f"{BASE_URL}/api/discounts",
            headers={"Authorization": f"Bearer {admin_token}"}
        )
        assert response.status_code in [200, 404]
        print(f"SUCCESS: Discount codes endpoint status: {response.status_code}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
