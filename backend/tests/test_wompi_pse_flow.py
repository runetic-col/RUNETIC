"""
Test suite for WOMPI PSE Payment Flow - RUNETIC E-Commerce
Tests the fix for 'Token de aceptación ya fue usado' error.

Features tested:
1. WOMPI config returns PRODUCTION key (pub_prod_...)
2. POST /api/payments/wompi/register-attempt creates unique payment attempt
3. GET /api/payments/verify/{reference} returns payment status
4. Duplicate reference rejection
5. Unique reference generation pattern
"""
import pytest
import requests
import os
import time
import random
import string

BASE_URL = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')

# Test credentials
ADMIN_USERNAME = "Runetic.col"
ADMIN_PASSWORD = "1022378240RUNETICSA"


@pytest.fixture(scope="module")
def auth_token():
    """Get admin authentication token"""
    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
    )
    assert response.status_code == 200, f"Login failed: {response.text}"
    return response.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    """Get headers with auth token"""
    return {"Authorization": f"Bearer {auth_token}"}


def generate_unique_reference():
    """Generate unique reference similar to frontend logic"""
    timestamp = int(time.time() * 1000)
    random_str = ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
    return f"RUNETIC-{timestamp}-{random_str}"


class TestWOMPIConfig:
    """Test WOMPI payment gateway configuration"""
    
    def test_wompi_config_returns_production_key(self):
        """WOMPI config should return production public key (pub_prod_...)"""
        response = requests.get(f"{BASE_URL}/api/payments/wompi/config")
        assert response.status_code == 200
        
        data = response.json()
        assert "public_key" in data
        assert data["public_key"].startswith("pub_prod_"), \
            f"Expected production key (pub_prod_...), got: {data['public_key']}"
        assert data["public_key"] == "pub_prod_ZYEmuh53kkm4KCXQyfarBXyoA53htiRW"
        assert data["currency"] == "COP"
        assert data["country"] == "CO"
        print(f"✅ WOMPI production key verified: {data['public_key']}")


class TestPaymentAttemptRegistration:
    """Test payment attempt registration endpoint"""
    
    def test_register_payment_attempt_success(self):
        """Should successfully register a new payment attempt"""
        reference = generate_unique_reference()
        
        response = requests.post(
            f"{BASE_URL}/api/payments/wompi/register-attempt",
            json={
                "order_id": "test-order-001",
                "reference": reference,
                "amount_in_cents": 150000,
                "session_id": f"session_{int(time.time())}"
            }
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data["success"] == True
        assert data["reference"] == reference
        print(f"✅ Payment attempt registered: {reference}")
    
    def test_duplicate_reference_rejected(self):
        """Should reject duplicate payment reference"""
        reference = generate_unique_reference()
        
        # First attempt - should succeed
        response1 = requests.post(
            f"{BASE_URL}/api/payments/wompi/register-attempt",
            json={
                "order_id": "test-order-dup",
                "reference": reference,
                "amount_in_cents": 100000,
                "session_id": "session-1"
            }
        )
        assert response1.status_code == 200
        print(f"✅ First attempt succeeded: {reference}")
        
        # Second attempt with same reference - should fail
        response2 = requests.post(
            f"{BASE_URL}/api/payments/wompi/register-attempt",
            json={
                "order_id": "test-order-dup",
                "reference": reference,
                "amount_in_cents": 100000,
                "session_id": "session-2"
            }
        )
        assert response2.status_code == 400
        data = response2.json()
        assert "ya fue utilizada" in data["detail"]
        print(f"✅ Duplicate reference correctly rejected")
    
    def test_multiple_unique_references_allowed(self):
        """Should allow multiple unique references for same order"""
        order_id = "test-order-multi"
        
        references = []
        for i in range(3):
            reference = generate_unique_reference()
            references.append(reference)
            
            response = requests.post(
                f"{BASE_URL}/api/payments/wompi/register-attempt",
                json={
                    "order_id": order_id,
                    "reference": reference,
                    "amount_in_cents": 100000,
                    "session_id": f"session-{i}"
                }
            )
            assert response.status_code == 200
            time.sleep(0.1)  # Small delay to ensure unique timestamps
        
        print(f"✅ Multiple unique references allowed: {len(references)} attempts")


class TestPaymentVerification:
    """Test payment verification endpoint"""
    
    def test_verify_existing_payment(self):
        """Should return status for existing payment reference"""
        reference = generate_unique_reference()
        
        # First register the payment
        requests.post(
            f"{BASE_URL}/api/payments/wompi/register-attempt",
            json={
                "order_id": "test-verify-order",
                "reference": reference,
                "amount_in_cents": 100000,
                "session_id": "session-verify"
            }
        )
        
        # Verify the payment
        response = requests.get(f"{BASE_URL}/api/payments/verify/{reference}")
        assert response.status_code == 200
        
        data = response.json()
        assert data["reference"] == reference
        assert "status" in data
        # New payments should be INITIATED or PENDING
        assert data["status"] in ["INITIATED", "PENDING"]
        print(f"✅ Payment verification returned status: {data['status']}")
    
    def test_verify_nonexistent_payment(self):
        """Should return PENDING for non-existent reference"""
        response = requests.get(f"{BASE_URL}/api/payments/verify/NONEXISTENT-REF-12345")
        assert response.status_code == 200
        
        data = response.json()
        assert data["status"] == "PENDING"
        print(f"✅ Non-existent reference returns PENDING status")


class TestUniqueReferencePattern:
    """Test unique reference generation pattern"""
    
    def test_reference_format(self):
        """Reference should follow RUNETIC-{timestamp}-{random} pattern"""
        reference = generate_unique_reference()
        
        parts = reference.split("-")
        assert len(parts) == 3
        assert parts[0] == "RUNETIC"
        assert parts[1].isdigit()  # Timestamp
        assert len(parts[2]) == 8  # Random string
        print(f"✅ Reference format verified: {reference}")
    
    def test_references_are_unique(self):
        """Generated references should be unique"""
        references = set()
        for _ in range(100):
            ref = generate_unique_reference()
            assert ref not in references, f"Duplicate reference generated: {ref}"
            references.add(ref)
        
        print(f"✅ Generated {len(references)} unique references")


class TestOrderCreation:
    """Test order creation with payment flow"""
    
    def test_create_order_for_payment(self):
        """Should create order that can be used for payment"""
        # Get a product first
        products_response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert products_response.status_code == 200
        products = products_response.json()["products"]
        
        if not products:
            pytest.skip("No products available for testing")
        
        product = products[0]
        
        # Create order
        order_data = {
            "customer_type": "retail",
            "items": [{
                "product_id": product["id"],
                "product_code": product.get("code", "TEST-CODE"),
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
                "unit_price": product.get("base_price_retail", 100000),
                "total_price": product.get("base_price_retail", 100000)
            }],
            "shipping_address": {
                "full_name": "Test User PSE",
                "document_type": "CC",
                "document_id": "1234567890",
                "phone": "3001234567",
                "email": "test@example.com",
                "address": "Calle Test 123",
                "city": "Bogotá",
                "department": "Cundinamarca"
            },
            "payment_method": "wompi_pse",
            "size_confirmation": True
        }
        
        response = requests.post(f"{BASE_URL}/api/orders", json=order_data)
        assert response.status_code == 200
        
        data = response.json()
        assert "order_id" in data
        assert "order_number" in data
        print(f"✅ Order created: {data['order_number']}")
        
        # Now register payment attempt for this order
        reference = generate_unique_reference()
        payment_response = requests.post(
            f"{BASE_URL}/api/payments/wompi/register-attempt",
            json={
                "order_id": data["order_id"],
                "reference": reference,
                "amount_in_cents": int(product.get("base_price_retail", 100000) * 100),
                "session_id": f"session_{int(time.time())}"
            }
        )
        assert payment_response.status_code == 200
        print(f"✅ Payment attempt registered for order: {reference}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
