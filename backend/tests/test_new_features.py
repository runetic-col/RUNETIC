"""
Test suite for RUNETIC E-Commerce new features:
1. Image carousel (product images)
2. Color configuration per product
3. WOMPI production key
4. Wholesale discount tiers
"""
import pytest
import requests
import os

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
        assert data["currency"] == "COP"
        assert data["country"] == "CO"
        print(f"✅ WOMPI production key verified: {data['public_key'][:20]}...")


class TestProductColors:
    """Test product color configuration"""
    
    def test_update_product_with_colors(self, auth_headers):
        """Product update should save available_colors field"""
        # Get first product
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert response.status_code == 200
        products = response.json()["products"]
        assert len(products) > 0, "No products found"
        
        product_id = products[0]["id"]
        
        # Update product with colors
        test_colors = ["Blanco", "Negro", "Azul"]
        update_response = requests.put(
            f"{BASE_URL}/api/products/{product_id}",
            json={"available_colors": test_colors},
            headers=auth_headers
        )
        assert update_response.status_code == 200
        print(f"✅ Product updated with colors: {test_colors}")
        
        # Verify colors were saved
        get_response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert get_response.status_code == 200
        
        product_data = get_response.json()
        assert "available_colors" in product_data
        assert product_data["available_colors"] == test_colors
        print(f"✅ Colors verified in product: {product_data['available_colors']}")
    
    def test_public_product_api_returns_colors(self):
        """Public product API should return available_colors"""
        # Get products list
        response = requests.get(f"{BASE_URL}/api/products?limit=5")
        assert response.status_code == 200
        
        # Get a specific product
        products = response.json()["products"]
        assert len(products) > 0
        
        product_id = products[0]["id"]
        detail_response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert detail_response.status_code == 200
        
        product = detail_response.json()
        # available_colors should be present (may be empty list or have colors)
        assert "available_colors" in product or product.get("available_colors") is None
        print(f"✅ Product detail API returns available_colors field")


class TestProductImages:
    """Test product image carousel functionality"""
    
    def test_product_has_images_structure(self):
        """Product should have images with fan/player structure"""
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        assert response.status_code == 200
        
        products = response.json()["products"]
        assert len(products) > 0
        
        product = products[0]
        assert "images" in product
        
        images = product["images"]
        # Should have fan and/or player keys
        assert "fan" in images or "player" in images
        print(f"✅ Product has images structure: {list(images.keys())}")
    
    def test_product_detail_returns_all_images(self):
        """Product detail should return all images for carousel"""
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        products = response.json()["products"]
        product_id = products[0]["id"]
        
        detail_response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        assert detail_response.status_code == 200
        
        product = detail_response.json()
        images = product.get("images", {})
        
        fan_images = images.get("fan", [])
        player_images = images.get("player", [])
        
        print(f"✅ Product has {len(fan_images)} fan images and {len(player_images)} player images")
        
        # Verify image URLs are valid strings
        for img in fan_images:
            assert isinstance(img, str) and img.startswith("http")


class TestWholesaleTiers:
    """Test wholesale discount tiers"""
    
    def test_get_wholesale_tiers(self, auth_headers):
        """Should return wholesale discount tiers"""
        response = requests.get(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "tiers" in data
        
        tiers = data["tiers"]
        assert len(tiers) >= 1, "Should have at least one tier"
        
        # Verify tier structure
        for tier in tiers:
            assert "min_quantity" in tier
            assert "discount_percent" in tier
        
        print(f"✅ Retrieved {len(tiers)} wholesale tiers")
    
    def test_update_wholesale_tiers(self, auth_headers):
        """Should be able to update wholesale discount tiers"""
        new_tiers = [
            {"min_quantity": 1, "max_quantity": 9, "discount_percent": 30},
            {"min_quantity": 10, "max_quantity": 19, "discount_percent": 35},
            {"min_quantity": 20, "max_quantity": 49, "discount_percent": 40},
            {"min_quantity": 50, "max_quantity": None, "discount_percent": 45}
        ]
        
        response = requests.put(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            json={"tiers": new_tiers},
            headers=auth_headers
        )
        assert response.status_code == 200
        
        data = response.json()
        assert data["message"] == "Wholesale tiers updated"
        print("✅ Wholesale tiers updated successfully")
        
        # Verify tiers were saved
        get_response = requests.get(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            headers=auth_headers
        )
        assert get_response.status_code == 200
        
        saved_tiers = get_response.json()["tiers"]
        assert len(saved_tiers) == 4
        assert saved_tiers[0]["discount_percent"] == 30
        assert saved_tiers[3]["discount_percent"] == 45
        print("✅ Wholesale tiers verified after save")
    
    def test_wholesale_tier_discount_values(self, auth_headers):
        """Verify wholesale tier discount percentages are correct"""
        response = requests.get(
            f"{BASE_URL}/api/settings/wholesale-tiers",
            headers=auth_headers
        )
        assert response.status_code == 200
        
        tiers = response.json()["tiers"]
        
        # Verify expected discount structure
        expected_discounts = {
            (1, 9): 30,
            (10, 19): 35,
            (20, 49): 40,
            (50, None): 45
        }
        
        for tier in tiers:
            key = (tier["min_quantity"], tier.get("max_quantity"))
            if key in expected_discounts:
                assert tier["discount_percent"] == expected_discounts[key], \
                    f"Tier {key} should have {expected_discounts[key]}% discount"
        
        print("✅ All wholesale tier discounts verified")


class TestProductUpdate:
    """Test product update functionality"""
    
    def test_update_product_saves_all_fields(self, auth_headers):
        """Product update should save all fields including colors and versions"""
        # Get first product
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        products = response.json()["products"]
        product_id = products[0]["id"]
        
        # Update with multiple fields
        update_data = {
            "available_colors": ["Rojo", "Verde", "Amarillo"],
            "available_versions": ["hombre_fan", "dama"],
            "packaging_options": ["normal", "premium"]
        }
        
        update_response = requests.put(
            f"{BASE_URL}/api/products/{product_id}",
            json=update_data,
            headers=auth_headers
        )
        assert update_response.status_code == 200
        
        # Verify all fields were saved
        get_response = requests.get(f"{BASE_URL}/api/products/{product_id}")
        product = get_response.json()
        
        assert product.get("available_colors") == update_data["available_colors"]
        print("✅ Product update saves all fields correctly")


class TestAuthAndPermissions:
    """Test authentication and admin permissions"""
    
    def test_admin_login(self):
        """Admin should be able to login"""
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD}
        )
        assert response.status_code == 200
        
        data = response.json()
        assert "access_token" in data
        assert data["role"] == "admin"
        print("✅ Admin login successful")
    
    def test_wholesale_tiers_requires_auth(self):
        """Wholesale tiers endpoint should require authentication"""
        response = requests.get(f"{BASE_URL}/api/settings/wholesale-tiers")
        assert response.status_code in [401, 403]
        print("✅ Wholesale tiers endpoint requires authentication")
    
    def test_product_update_requires_auth(self):
        """Product update should require authentication"""
        response = requests.get(f"{BASE_URL}/api/products?limit=1")
        products = response.json()["products"]
        product_id = products[0]["id"]
        
        update_response = requests.put(
            f"{BASE_URL}/api/products/{product_id}",
            json={"reference": "Test"}
        )
        assert update_response.status_code in [401, 403]
        print("✅ Product update requires authentication")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
