"""
RUNETIC E-Commerce Tests - Iteration 10
Testing: Access differentiation, Login pages, Admin Dashboard, Home sections, Checkout flows (COD/Transfer)
"""

import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ecommerce-fixes-14.preview.emergentagent.com').rstrip('/')


class TestAuthEndpoints:
    """Test authentication endpoints for Admin and Mayorista"""
    
    def test_admin_login_success(self):
        """Test admin login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "Runetic.col",
            "password": "1022378240RUNETICSA"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "admin"
        print("Admin login: PASS")
    
    def test_mayorista_login_success(self):
        """Test mayorista login with valid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "RuneticMayorista",
            "password": "RuneticM102"
        })
        assert response.status_code == 200
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "mayorista"
        print("Mayorista login: PASS")
    
    def test_invalid_login(self):
        """Test login with invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "invalid_user",
            "password": "wrong_password"
        })
        assert response.status_code == 401
        print("Invalid login rejected: PASS")


class TestCashOnDeliveryFlow:
    """Test Cash on Delivery order flow with token generation"""
    
    def test_create_cod_order_generates_token(self):
        """Test that COD orders generate a pickup token with correct format"""
        order_data = {
            "customer_type": "retail",
            "items": [
                {
                    "product_id": "test_cod_123",
                    "product_code": "RUN-COD-TEST",
                    "product_name": "Test COD Jersey",
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
                    "unit_price": 85000,
                    "total_price": 85000
                }
            ],
            "shipping_address": {
                "full_name": "Test COD User",
                "document_type": "CC",
                "document_id": "111222333",
                "phone": "3101234567",
                "email": "testcod@test.com",
                "address": "Calle Test #123",
                "city": "Bogotá",
                "department": "Cundinamarca"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 85000,
            "total_amount": 100000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        
        result = response.json()
        assert "order_id" in result
        assert "pickup_token" in result
        
        # Verify token format starts with COD-
        token = result.get('pickup_token')
        assert token is not None
        assert token.startswith('COD-')
        assert len(token) == 12  # COD-XXXXXXXX
        
        print(f"COD order created with token {token}: PASS")
        
        # Verify order details persist the token
        order_id = result.get('order_id')
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        assert order_resp.status_code == 200
        
        order_details = order_resp.json()
        assert order_details.get('pickup_token') == token
        assert order_details.get('pickup_token_used') == False
        assert order_details.get('payment_method') == 'cash_on_delivery'
        
        print("COD order token persistence: PASS")


class TestBankTransferFlow:
    """Test Bank Transfer order flow"""
    
    def test_create_transfer_order_no_token(self):
        """Test that bank transfer orders do NOT generate a pickup token"""
        order_data = {
            "customer_type": "retail",
            "items": [
                {
                    "product_id": "test_transfer_456",
                    "product_code": "RUN-TRANSFER-TEST",
                    "product_name": "Test Transfer Jersey",
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
                    "unit_price": 90000,
                    "total_price": 90000
                }
            ],
            "shipping_address": {
                "full_name": "Test Transfer User",
                "document_type": "CC",
                "document_id": "444555666",
                "phone": "3109876543",
                "email": "testtransfer@test.com",
                "address": "Carrera Test #456",
                "city": "Medellín",
                "department": "Antioquia"
            },
            "payment_method": "bank_transfer",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": 90000,
            "total_amount": 105000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        
        result = response.json()
        assert "order_id" in result
        
        # Bank transfer should NOT have a pickup token
        assert result.get('pickup_token') is None
        
        print("Bank transfer order created without token: PASS")
        
        # Verify order details
        order_id = result.get('order_id')
        order_resp = requests.get(f"{BASE_URL}/api/orders/{order_id}")
        assert order_resp.status_code == 200
        
        order_details = order_resp.json()
        assert order_details.get('payment_method') == 'bank_transfer'
        assert 'order_number' in order_details
        
        print("Bank transfer order details: PASS")


class TestProductEndpoints:
    """Test product-related endpoints"""
    
    def test_get_products_list(self):
        """Test getting list of products"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data
        assert isinstance(data["products"], list)
        
        print(f"Products list returned {len(data['products'])} products: PASS")
    
    def test_get_featured_products(self):
        """Test getting featured products"""
        response = requests.get(f"{BASE_URL}/api/products/featured/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data
        
        print(f"Featured products: {len(data['products'])} items: PASS")
    
    def test_get_on_sale_products(self):
        """Test getting products on sale"""
        response = requests.get(f"{BASE_URL}/api/products/on-sale/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data
        
        print(f"On sale products: {len(data['products'])} items: PASS")
    
    def test_get_seasonal_products(self):
        """Test getting seasonal products"""
        response = requests.get(f"{BASE_URL}/api/products/seasonal/list")
        assert response.status_code == 200
        
        data = response.json()
        assert "products" in data
        
        print(f"Seasonal products: {len(data['products'])} items: PASS")


class TestDiscountCodeEndpoints:
    """Test discount code validation"""
    
    def test_validate_invalid_code(self):
        """Test validating an invalid discount code"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "INVALID_CODE_12345"
        })
        # Should return 400 or 404 for invalid code
        assert response.status_code in [400, 404]
        print("Invalid discount code rejected: PASS")


class TestHealthEndpoint:
    """Test API health"""
    
    def test_health_check(self):
        """Test the API is accessible via products endpoint"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        print("API health check (products endpoint): PASS")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
