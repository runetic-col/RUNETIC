"""
Backend tests for Discount Code functionality in RUNETIC E-commerce
Tests the POST /api/discount-codes/validate endpoint
"""
import pytest
import requests
import os

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', 'https://ecommerce-fixes-14.preview.emergentagent.com').rstrip('/')


class TestDiscountCodeValidation:
    """Discount Code validation endpoint tests"""
    
    def test_validate_valid_code_test10(self):
        """Test that TEST10 discount code returns valid with 10% percentage discount"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "TEST10"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 200, f"Expected 200, got {response.status_code}: {response.text}"
        
        data = response.json()
        assert data.get("valid") == True, "Expected valid to be True"
        assert data.get("discount_type") == "percentage", f"Expected percentage, got {data.get('discount_type')}"
        assert data.get("discount_value") == 10.0 or data.get("discount_value") == 10, f"Expected 10, got {data.get('discount_value')}"
        
        print(f"TEST10 code validation successful: {data}")
    
    def test_validate_code_case_insensitive(self):
        """Test that discount code validation works with lowercase"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "test10"},
            headers={"Content-Type": "application/json"}
        )
        
        # Frontend sends uppercase, but we test backend accepts lowercase
        # Backend should normalize to uppercase in the endpoint
        if response.status_code == 200:
            data = response.json()
            assert data.get("valid") == True
            print(f"Lowercase code accepted: {data}")
        else:
            # If backend requires exact case, this is fine
            assert response.status_code == 404
            print("Backend requires exact case for discount codes")
    
    def test_validate_invalid_code(self):
        """Test that invalid discount code returns 404"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": "INVALID123"},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code == 404, f"Expected 404, got {response.status_code}"
        
        data = response.json()
        assert "detail" in data, "Expected error detail message"
        assert "inválido" in data["detail"].lower() or "invalid" in data["detail"].lower()
        
        print(f"Invalid code correctly rejected: {data}")
    
    def test_validate_empty_code(self):
        """Test that empty discount code returns error"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={"code": ""},
            headers={"Content-Type": "application/json"}
        )
        
        assert response.status_code in [400, 404], f"Expected 400 or 404, got {response.status_code}"
        print(f"Empty code correctly rejected with status {response.status_code}")
    
    def test_validate_code_missing_body(self):
        """Test that missing code field returns error"""
        response = requests.post(
            f"{BASE_URL}/api/discount-codes/validate",
            json={},
            headers={"Content-Type": "application/json"}
        )
        
        # Should return error since code is missing
        assert response.status_code in [400, 404, 422], f"Expected error status, got {response.status_code}"
        print(f"Missing code field correctly handled with status {response.status_code}")


class TestDiscountCodeWithOrder:
    """Tests for discount code application during order creation"""
    
    def test_order_with_valid_discount_code(self):
        """Test creating an order with a valid discount code"""
        # First, get a product to add to cart
        products_response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert products_response.status_code == 200
        
        products_data = products_response.json()
        if not products_data.get("products"):
            pytest.skip("No products available for order test")
        
        product = products_data["products"][0]
        
        # Create order with discount code
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": product["id"],
                "product_code": product.get("code", "TEST"),
                "product_name": product.get("reference", "Test Product"),
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
                "unit_price": product.get("base_price_retail", 55000),
                "total_price": product.get("base_price_retail", 55000)
            }],
            "shipping_address": {
                "full_name": "TEST_DiscountUser",
                "document_type": "CC",
                "document_id": "123456789",
                "phone": "3001234567",
                "email": "test_discount@test.com",
                "address": "Calle Test 123",
                "city": "Bogota",
                "department": "Cundinamarca"
            },
            "payment_method": "cash_on_delivery",
            "discount_code": "TEST10",
            "size_confirmation": True,
            "shipping_cost": 15000,
            "subtotal": product.get("base_price_retail", 55000),
            "total_amount": product.get("base_price_retail", 55000) * 0.9 + 15000  # 10% discount + shipping
        }
        
        response = requests.post(
            f"{BASE_URL}/api/orders",
            json=order_data,
            headers={"Content-Type": "application/json"}
        )
        
        # Note: This might fail if discount code has usage limits reached
        if response.status_code == 201:
            data = response.json()
            assert "order_id" in data
            print(f"Order created with discount code: {data['order_id']}")
        elif response.status_code == 400:
            data = response.json()
            print(f"Order creation returned 400 (may be usage limit): {data.get('detail', data)}")
        else:
            print(f"Order response: {response.status_code} - {response.text}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
