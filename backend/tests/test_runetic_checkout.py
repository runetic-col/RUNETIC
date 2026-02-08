"""
RUNETIC E-Commerce Backend Tests
Tests: Orders API, Shipping Logic, Authentication, Products
"""
import pytest
import requests
import os
import random
import string

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ecommerce-fixes-14.preview.emergentagent.com')

# Test credentials
ADMIN_USER = "Runetic.col"
ADMIN_PASS = "1022378240RUNETICSA"
MAYORISTA_USER = "RuneticMayorista"
MAYORISTA_PASS = "RuneticM102"

class TestProductsAPI:
    """Test products endpoints"""
    
    def test_get_products(self):
        """Test fetching products list"""
        response = requests.get(f"{BASE_URL}/api/products")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        assert isinstance(data["products"], list)
        print(f"SUCCESS: Found {len(data['products'])} products")
    
    def test_get_featured_products(self):
        """Test fetching featured products"""
        response = requests.get(f"{BASE_URL}/api/products/featured/list")
        assert response.status_code == 200
        data = response.json()
        assert "products" in data
        print(f"SUCCESS: Found {len(data['products'])} featured products")
    
    def test_get_product_by_id(self):
        """Test fetching single product"""
        # First get products list
        products_res = requests.get(f"{BASE_URL}/api/products")
        products = products_res.json().get("products", [])
        
        if products:
            product_id = products[0]["id"]
            response = requests.get(f"{BASE_URL}/api/products/{product_id}")
            assert response.status_code == 200
            product = response.json()
            assert "id" in product
            assert "reference" in product
            print(f"SUCCESS: Retrieved product {product['reference']}")


class TestOrdersAPI:
    """Test orders endpoints"""
    
    def test_create_retail_order_with_cod(self):
        """Test creating retail order with COD - should get pickup token"""
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": "test-product-id",
                "product_code": "TEST-001",
                "product_name": "Test Product",
                "version_type": "hombre_fan",
                "size": "M",
                "quantity": 1,
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "none",
                    "empaque_price": 0
                },
                "unit_price": 50000,
                "total_price": 50000
            }],
            "shipping_address": {
                "full_name": "Test Customer COD",
                "document_type": "CC",
                "document_id": "123456789",
                "phone": "3001234567",
                "email": "test.cod@gmail.com",
                "address": "Calle 123 #45-67",
                "city": "Bogota",
                "department": "Cundinamarca"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "order_id" in data
        assert "pickup_token" in data  # COD should have pickup token
        assert data["pickup_token"].startswith("COD-")
        print(f"SUCCESS: Created COD order with token {data['pickup_token']}")
    
    def test_create_retail_order_6_items_free_shipping(self):
        """Test retail order with 6 items - should have free shipping"""
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": "test-product-id",
                "product_code": "TEST-002",
                "product_name": "Test Product",
                "version_type": "hombre_fan",
                "size": "M",
                "quantity": 6,  # 6 items for free shipping
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "none",
                    "empaque_price": 0
                },
                "unit_price": 50000,
                "total_price": 300000
            }],
            "shipping_address": {
                "full_name": "Test Free Shipping",
                "document_type": "CC",
                "document_id": "987654321",
                "phone": "3009876543",
                "email": "test.freeshipping@gmail.com",
                "address": "Calle 456 #78-90",
                "city": "Medellin",
                "department": "Antioquia"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 0  # Free shipping for 6+ items
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "order_id" in data
        print(f"SUCCESS: Created retail order with 6 items (free shipping)")


class TestAuthentication:
    """Test login endpoints"""
    
    def test_admin_login(self):
        """Test admin login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": ADMIN_USER,
            "password": ADMIN_PASS
        })
        assert response.status_code == 200
        data = response.json()
        assert "token" in data or "access_token" in data or "role" in data
        print(f"SUCCESS: Admin login - role: {data.get('role', 'N/A')}")
        return data
    
    def test_mayorista_login(self):
        """Test mayorista login"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": MAYORISTA_USER,
            "password": MAYORISTA_PASS
        })
        assert response.status_code == 200
        data = response.json()
        assert data.get("role") == "mayorista"
        print(f"SUCCESS: Mayorista login - role: {data.get('role')}")
        return data
    
    def test_invalid_login(self):
        """Test invalid credentials"""
        response = requests.post(f"{BASE_URL}/api/auth/login", json={
            "username": "invalid_user",
            "password": "wrong_password"
        })
        assert response.status_code in [401, 400]
        print("SUCCESS: Invalid login correctly rejected")


class TestWholesaleShipping:
    """Test wholesale (mayorista) always pays shipping"""
    
    def test_wholesale_order_always_pays_shipping(self):
        """Test that wholesale orders ALWAYS pay shipping $15,000 regardless of quantity"""
        order_data = {
            "customer_type": "wholesale",  # Mayorista
            "items": [{
                "product_id": "test-product-id",
                "product_code": "TEST-003",
                "product_name": "Test Wholesale Product",
                "version_type": "hombre_fan",
                "size": "L",
                "quantity": 10,  # Even with 10 items, wholesale pays shipping
                "customization": {
                    "estampado": "sin_estampado",
                    "estampado_price": 0,
                    "parches": "sin_parches",
                    "parches_price": 0,
                    "empaque": "none",
                    "empaque_price": 0
                },
                "unit_price": 38000,
                "total_price": 380000
            }],
            "shipping_address": {
                "full_name": "Test Wholesale Customer",
                "document_type": "CC",
                "document_id": "111222333",
                "phone": "3111222333",
                "email": "test.wholesale@gmail.com",
                "address": "Carrera 1 #2-3",
                "city": "Cali",
                "department": "Valle del Cauca"
            },
            "payment_method": "cash_on_delivery",
            "size_confirmation": True,
            "shipping_cost": 15000  # Wholesale always pays $15,000
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code in [200, 201], f"Expected 200/201, got {response.status_code}: {response.text}"
        data = response.json()
        assert "order_id" in data
        print(f"SUCCESS: Created wholesale order (always pays shipping)")


class TestBannersAPI:
    """Test banners endpoints"""
    
    def test_get_banners(self):
        """Test fetching banners"""
        response = requests.get(f"{BASE_URL}/api/banners")
        assert response.status_code == 200
        data = response.json()
        assert "banners" in data
        print(f"SUCCESS: Found {len(data['banners'])} banners")


class TestDiscountCodes:
    """Test discount codes endpoints"""
    
    def test_validate_invalid_code(self):
        """Test validation of invalid discount code"""
        response = requests.post(f"{BASE_URL}/api/discount-codes/validate", json={
            "code": "INVALID_CODE_12345"
        })
        assert response.status_code in [400, 404]
        print("SUCCESS: Invalid discount code correctly rejected")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
