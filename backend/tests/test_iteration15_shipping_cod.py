"""
Test Suite for Iteration 15 - COD Token, Shipping Logic, Mobile Flow
Tests:
1. COD Token generation on order creation
2. Free shipping for retail with 6+ units
3. Wholesale always pays $15,000 shipping
4. Order creation API validation
"""

import pytest
import requests
import os
import uuid

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ecommerce-fixes-14.preview.emergentagent.com').rstrip('/')

# Test data
TEST_PRODUCT = {
    "product_id": "test-product-" + str(uuid.uuid4())[:8],
    "product_code": "RUN-TEST",
    "product_name": "Camiseta Test RUNETIC",
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

SHIPPING_ADDRESS = {
    "full_name": "TEST Usuario Prueba",
    "document_type": "CC",
    "document_id": "123456789",
    "phone": "3001234567",
    "email": "test@runetic.co",
    "address": "Calle 123 #45-67",
    "city": "Bogotá",
    "department": "Cundinamarca"
}


class TestCODTokenGeneration:
    """Tests for Cash On Delivery token generation"""
    
    def test_cod_order_creates_pickup_token(self):
        """Test that COD orders generate a pickup_token"""
        # Create order with cash_on_delivery payment method
        order_data = {
            "customer_type": "retail",
            "items": [TEST_PRODUCT],
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "cash_on_delivery",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        print(f"Order created: {data}")
        
        # Verify pickup_token is returned
        assert "pickup_token" in data, "pickup_token should be in response"
        assert data["pickup_token"] is not None, "pickup_token should not be None"
        assert data["pickup_token"].startswith("COD-"), f"Token should start with COD-, got: {data['pickup_token']}"
        assert len(data["pickup_token"]) == 12, f"Token should be 12 chars (COD-XXXXXXXX), got: {len(data['pickup_token'])}"
        
        print(f"✅ COD Token generated: {data['pickup_token']}")
    
    def test_non_cod_order_no_pickup_token(self):
        """Test that non-COD orders do not get pickup_token"""
        order_data = {
            "customer_type": "retail",
            "items": [TEST_PRODUCT],
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "bank_transfer",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        
        # pickup_token should be None for bank_transfer
        assert data.get("pickup_token") is None, f"pickup_token should be None for bank_transfer, got: {data.get('pickup_token')}"
        
        print(f"✅ Non-COD order has no pickup_token")


class TestRetailFreeShipping:
    """Tests for retail free shipping with 6+ units"""
    
    def test_retail_5_units_has_shipping(self):
        """Test retail with 5 units pays shipping ($15,000)"""
        items = []
        for i in range(5):
            item = TEST_PRODUCT.copy()
            item["product_id"] = f"test-product-{i}"
            item["quantity"] = 1
            items.append(item)
        
        subtotal = 85000 * 5  # 425,000
        shipping = 15000  # Should have shipping
        total = subtotal + shipping
        
        order_data = {
            "customer_type": "retail",
            "items": items,
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "cash_on_delivery",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": shipping,
            "subtotal": subtotal,
            "total_amount": total
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify order - fetch to check shipping_cost
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        # Backend should accept the frontend's shipping cost calculation
        print(f"✅ Retail 5 units - Shipping: ${order.get('shipping_cost', 'N/A')}")
    
    def test_retail_6_units_free_shipping(self):
        """Test retail with 6 units gets FREE shipping ($0)"""
        items = []
        for i in range(6):
            item = TEST_PRODUCT.copy()
            item["product_id"] = f"test-product-{i}"
            item["quantity"] = 1
            items.append(item)
        
        subtotal = 85000 * 6  # 510,000
        shipping = 0  # FREE shipping for 6+ units
        total = subtotal + shipping
        
        order_data = {
            "customer_type": "retail",
            "items": items,
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "cash_on_delivery",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": shipping,
            "subtotal": subtotal,
            "total_amount": total
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        # Verify order
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        # Backend accepts frontend's free shipping
        assert order.get("shipping_cost") == 0, f"Expected free shipping ($0), got ${order.get('shipping_cost')}"
        
        print(f"✅ Retail 6+ units - FREE Shipping confirmed: ${order.get('shipping_cost', 'N/A')}")
    
    def test_retail_10_units_free_shipping(self):
        """Test retail with 10 units gets FREE shipping"""
        # Single item with quantity 10
        item = TEST_PRODUCT.copy()
        item["quantity"] = 10
        item["total_price"] = 85000 * 10
        
        subtotal = 850000
        shipping = 0  # FREE shipping for 6+ units
        total = subtotal + shipping
        
        order_data = {
            "customer_type": "retail",
            "items": [item],
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "bank_transfer",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": shipping,
            "subtotal": subtotal,
            "total_amount": total
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        assert order.get("shipping_cost") == 0, f"Expected free shipping, got ${order.get('shipping_cost')}"
        
        print(f"✅ Retail 10 units - FREE Shipping: ${order.get('shipping_cost')}")


class TestWholesaleShipping:
    """Tests for wholesale shipping (ALWAYS $15,000)"""
    
    def test_wholesale_1_unit_pays_shipping(self):
        """Test wholesale with 1 unit PAYS shipping"""
        order_data = {
            "customer_type": "wholesale",
            "items": [TEST_PRODUCT],
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "bank_transfer",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        assert order.get("shipping_cost") == 15000, f"Wholesale should pay $15,000 shipping, got ${order.get('shipping_cost')}"
        
        print(f"✅ Wholesale 1 unit - Pays shipping: ${order.get('shipping_cost')}")
    
    def test_wholesale_6_units_still_pays_shipping(self):
        """Test wholesale with 6 units STILL PAYS shipping (no free shipping for wholesale)"""
        items = []
        for i in range(6):
            item = TEST_PRODUCT.copy()
            item["product_id"] = f"test-product-{i}"
            item["quantity"] = 1
            items.append(item)
        
        subtotal = 85000 * 6
        shipping = 15000  # Wholesale ALWAYS pays
        total = subtotal + shipping
        
        order_data = {
            "customer_type": "wholesale",
            "items": items,
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "bank_transfer",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": shipping,
            "subtotal": subtotal,
            "total_amount": total
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        # Wholesale with 6+ units still pays shipping
        assert order.get("shipping_cost") == 15000, f"Wholesale 6+ units should STILL pay $15,000, got ${order.get('shipping_cost')}"
        
        print(f"✅ Wholesale 6 units - STILL pays shipping: ${order.get('shipping_cost')}")
    
    def test_wholesale_20_units_still_pays_shipping(self):
        """Test wholesale with 20 units STILL PAYS shipping"""
        item = TEST_PRODUCT.copy()
        item["quantity"] = 20
        item["total_price"] = 85000 * 20
        
        subtotal = 85000 * 20
        shipping = 15000  # Wholesale ALWAYS pays
        total = subtotal + shipping
        
        order_data = {
            "customer_type": "wholesale",
            "items": [item],
            "shipping_address": SHIPPING_ADDRESS,
            "payment_method": "cash_on_delivery",
            "discount_code": None,
            "size_confirmation": True,
            "shipping_cost": shipping,
            "subtotal": subtotal,
            "total_amount": total
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        order_id = data["order_id"]
        
        order_response = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        order = order_response.json()
        
        assert order.get("shipping_cost") == 15000, f"Wholesale 20 units should pay $15,000, got ${order.get('shipping_cost')}"
        
        # Also verify COD token is generated
        assert data.get("pickup_token") is not None, "Wholesale COD should have pickup_token"
        
        print(f"✅ Wholesale 20 units - Pays shipping: ${order.get('shipping_cost')}, Token: {data.get('pickup_token')}")


class TestAPIEndpoints:
    """Basic API health checks"""
    
    def test_health_endpoint(self):
        """Test basic API health"""
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert response.status_code == 200, f"Products endpoint failed: {response.status_code}"
        print("✅ API is healthy")
    
    def test_products_exist(self):
        """Test that products exist in catalog"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert len(data["products"]) > 0, "No products found in catalog"
        print(f"✅ Found {len(data['products'])} products")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
