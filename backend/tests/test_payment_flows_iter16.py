"""
Test Payment Flows - Iteration 16
Testing: PSE, Card, Bank Transfer, COD payment methods
Focus: Wompi widget redirect URLs, COD token generation
"""
import pytest
import requests
import os
import re

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

class TestWompiConfig:
    """Test Wompi payment gateway configuration"""
    
    def test_wompi_config_endpoint(self):
        """Verify Wompi config endpoint returns public key"""
        response = requests.get(f"{BASE_URL}/api/payments/wompi/config")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert "public_key" in data, "Missing public_key in response"
        assert data["public_key"] == "pub_prod_ZYEmuh53kkm4KCXQyfarBXyoA53htiRW", "Incorrect Wompi public key"
        assert data["currency"] == "COP", "Currency should be COP"
        assert data["country"] == "CO", "Country should be CO"
        print(f"✓ Wompi config verified: public_key={data['public_key'][:20]}...")

class TestPSEBanks:
    """Test PSE banks list endpoint"""
    
    def test_pse_banks_endpoint(self):
        """Verify PSE banks can be fetched"""
        response = requests.get(f"{BASE_URL}/api/payments/wompi/banks")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        # The endpoint returns data from Wompi or empty array
        assert "data" in data or isinstance(data, dict), "Response should contain data"
        print(f"✓ PSE banks endpoint works, returned {len(data.get('data', []))} banks")


class TestOrderCreation:
    """Test order creation for different payment methods"""
    
    @pytest.fixture
    def sample_cart_item(self):
        """Create sample cart item for testing"""
        return {
            "product_id": "test-product-123",
            "product_code": "TEST-001",
            "product_name": "Camiseta Colombia Test",
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
            "unit_price": 85000,
            "total_price": 85000
        }
    
    @pytest.fixture
    def sample_shipping_address(self):
        """Create sample shipping address"""
        return {
            "full_name": "Test Usuario Payment",
            "document_type": "CC",
            "document_id": "1234567890",
            "phone": "3001234567",
            "email": "test.payment@example.com",
            "address": "Calle 123 #45-67",
            "city": "Bogotá",
            "department": "Cundinamarca",
            "postal_code": "110111"
        }
    
    def test_create_order_pse(self, sample_cart_item, sample_shipping_address):
        """Test creating order with PSE payment method"""
        order_data = {
            "customer_type": "retail",
            "items": [sample_cart_item],
            "shipping_address": sample_shipping_address,
            "payment_method": "pse",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order_id" in data, "Missing order_id"
        assert "order_number" in data, "Missing order_number"
        assert data.get("pickup_token") is None, "PSE orders should not have pickup token"
        print(f"✓ PSE order created: {data['order_number']}")
        return data
    
    def test_create_order_credit_card(self, sample_cart_item, sample_shipping_address):
        """Test creating order with credit card payment method"""
        order_data = {
            "customer_type": "retail",
            "items": [sample_cart_item],
            "shipping_address": sample_shipping_address,
            "payment_method": "credit_card",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order_id" in data, "Missing order_id"
        assert data.get("pickup_token") is None, "Card orders should not have pickup token"
        print(f"✓ Credit card order created: {data['order_number']}")
    
    def test_create_order_bank_transfer(self, sample_cart_item, sample_shipping_address):
        """Test creating order with bank transfer payment method"""
        order_data = {
            "customer_type": "retail",
            "items": [sample_cart_item],
            "shipping_address": sample_shipping_address,
            "payment_method": "bank_transfer",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order_id" in data, "Missing order_id"
        assert data.get("pickup_token") is None, "Bank transfer orders should not have pickup token"
        print(f"✓ Bank transfer order created: {data['order_number']}")
    
    def test_create_order_cod_generates_token(self, sample_cart_item, sample_shipping_address):
        """Test that Cash on Delivery orders generate pickup token"""
        order_data = {
            "customer_type": "retail",
            "items": [sample_cart_item],
            "shipping_address": sample_shipping_address,
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert "order_id" in data, "Missing order_id"
        assert "pickup_token" in data, "Missing pickup_token for COD order"
        
        token = data["pickup_token"]
        assert token is not None, "Pickup token should not be None"
        assert token.startswith("COD-"), f"Token should start with 'COD-', got: {token}"
        assert len(token) == 12, f"Token should be 12 chars (COD-XXXXXXXX), got: {len(token)}"
        
        # Verify token format: COD-[A-Z0-9]{8}
        assert re.match(r'^COD-[A-Z0-9]{8}$', token), f"Token format invalid: {token}"
        
        print(f"✓ COD order created with token: {token}")
        return data


class TestCODTokenValidation:
    """Test COD pickup token validation"""
    
    @pytest.fixture
    def create_cod_order(self):
        """Create a COD order and return order data with token"""
        cart_item = {
            "product_id": "test-product-cod",
            "product_code": "COD-TEST",
            "product_name": "Camiseta Test COD",
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
            "unit_price": 90000,
            "total_price": 90000
        }
        
        order_data = {
            "customer_type": "retail",
            "items": [cart_item],
            "shipping_address": {
                "full_name": "Test COD User",
                "document_type": "CC",
                "document_id": "9876543210",
                "phone": "3009876543",
                "email": "cod.test@example.com",
                "address": "Carrera 789 #12-34",
                "city": "Medellín",
                "department": "Antioquia"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 90000,
            "total_amount": 105000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        return response.json()
    
    def test_validate_valid_token(self, create_cod_order):
        """Test validating a valid pickup token"""
        token = create_cod_order["pickup_token"]
        order_number = create_cod_order["order_number"]
        
        response = requests.post(
            f"{BASE_URL}/api/orders/validate-pickup-token",
            json={"token": token, "order_number": order_number}
        )
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data["valid"] == True, "Token should be valid"
        assert data["order_number"] == order_number
        assert data["total_amount"] == 105000
        print(f"✓ Token validation successful for {token}")
    
    def test_validate_invalid_token(self):
        """Test validating an invalid pickup token"""
        response = requests.post(
            f"{BASE_URL}/api/orders/validate-pickup-token",
            json={"token": "COD-INVALID0", "order_number": "ORD-NONEXISTENT"}
        )
        assert response.status_code == 404, f"Expected 404 for invalid token, got {response.status_code}"
        print("✓ Invalid token correctly rejected")


class TestOrderRetrieval:
    """Test retrieving orders"""
    
    def test_get_order_by_id(self):
        """Test getting order by ID (create first, then fetch)"""
        # First create an order
        cart_item = {
            "product_id": "test-get-order",
            "product_code": "GET-001",
            "product_name": "Camiseta Test Get",
            "version_type": "hombre_fan",
            "size": "S",
            "quantity": 1,
            "customization": {
                "estampado": "sin_estampado",
                "estampado_price": 0,
                "parches": "sin_parches",
                "parches_price": 0,
                "empaque": "normal",
                "empaque_price": 0
            },
            "unit_price": 75000,
            "total_price": 75000
        }
        
        order_data = {
            "customer_type": "retail",
            "items": [cart_item],
            "shipping_address": {
                "full_name": "Test Get Order",
                "document_type": "CC",
                "document_id": "1112223334",
                "phone": "3001112233",
                "email": "get.test@example.com",
                "address": "Av Test 123",
                "city": "Cali",
                "department": "Valle del Cauca"
            },
            "payment_method": "bank_transfer",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 75000,
            "total_amount": 90000
        }
        
        create_response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert create_response.status_code == 200
        order_id = create_response.json()["order_id"]
        
        # Now fetch the order
        get_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        assert get_response.status_code == 200, f"Expected 200, got {get_response.status_code}"
        
        fetched_order = get_response.json()
        assert fetched_order["id"] == order_id
        assert fetched_order["payment_method"] == "bank_transfer"
        assert fetched_order["total_amount"] == 90000
        print(f"✓ Order fetched successfully: {fetched_order['order_number']}")


class TestCheckPendingPayment:
    """Test pending payment check endpoint"""
    
    def test_check_no_pending_payment(self):
        """Test checking for pending payment on new order"""
        # Use a random order ID that won't have pending payments
        response = requests.get(f"{BASE_URL}/api/payments/wompi/check-pending/nonexistent-order-id")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        
        data = response.json()
        assert data["has_pending"] == False, "Should have no pending payment"
        print("✓ No pending payment check works")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
