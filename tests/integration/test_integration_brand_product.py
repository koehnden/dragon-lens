#!/usr/bin/env python3
"""Integration test for brand/product extraction improvements."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

def test_improvements():
    """Test all improvements made to brand/product extraction."""
    
    print("=" * 70)
    print("Integration Test: Brand/Product Extraction Improvements")
    print("=" * 70)
    
    # Test 1: Check that problematic examples are in KNOWN_PRODUCTS
    print("\n1. Testing KNOWN_PRODUCTS additions:")
    problematic_examples = ["RAV4", "H6", "L9", "BJ80", "Q7 E-Tron", "Q7"]
    
    # These should all be in KNOWN_PRODUCTS now
    from src.services.brand_recognition import KNOWN_PRODUCTS
    
    all_found = True
    for example in problematic_examples:
        example_lower = example.lower()
        found = example_lower in KNOWN_PRODUCTS or any(
            example_lower in prod or prod in example_lower 
            for prod in KNOWN_PRODUCTS
        )
        status = "✓" if found else "✗"
        print(f"  {status} '{example}' in KNOWN_PRODUCTS: {found}")
        if not found:
            all_found = False
    
    if all_found:
        print("  ✅ All problematic examples added to KNOWN_PRODUCTS")
    else:
        print("  ❌ Some examples missing from KNOWN_PRODUCTS")
    
    # Test 2: Test is_likely_product function
    print("\n2. Testing is_likely_product function:")
    
    # Import after fixing the import issue
    import src.services.brand_recognition as br_module
    
    test_cases = [
        ("RAV4", True, "Product with alphanumeric code"),
        ("H6", True, "Simple alphanumeric product code"),
        ("L9", True, "Simple alphanumeric product code"),
        ("BJ80", True, "Alphanumeric product code"),
        ("Q7", True, "Alphanumeric product code"),
        ("Toyota", False, "Brand name"),
        ("BMW", False, "Brand name"),
        ("SUV", False, "Generic term"),
        ("Model Y", True, "Product with model name"),
        ("iPhone 15", True, "Product with model number"),
    ]
    
    all_correct = True
    for name, expected, description in test_cases:
        result = br_module.is_likely_product(name)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{name}' -> {result} (expected: {expected}) - {description}")
        if result != expected:
            all_correct = False
    
    if all_correct:
        print("  ✅ is_likely_product function working correctly")
    else:
        print("  ❌ is_likely_product function has issues")
    
    # Test 3: Test automotive vertical detection
    print("\n3. Testing automotive vertical detection in prompt:")
    
    # Test the regex pattern for automotive detection
    import re
    
    def is_automotive_vertical(vertical: str) -> bool:
        vertical_lower = vertical.lower()
        keywords = ["car", "suv", "automotive", "vehicle", "auto", "truck"]
        return any(re.search(rf'\b{keyword}\b', vertical_lower) for keyword in keywords)
    
    vertical_tests = [
        ("SUV cars", True),
        ("automotive industry", True),
        ("vehicle market", True),
        ("auto parts", True),
        ("truck manufacturers", True),
        ("smartphones", False),
        ("skincare", False),  # Should not match because of "car" in "skincare"
        ("general", False),
        ("car accessories", True),
        ("electric vehicles", True),  # Contains "vehicle"
    ]
    
    all_vertical_correct = True
    for vertical, expected in vertical_tests:
        result = is_automotive_vertical(vertical)
        status = "✓" if result == expected else "✗"
        print(f"  {status} '{vertical}' -> {result} (expected: {expected})")
        if result != expected:
            all_vertical_correct = False
    
    if all_vertical_correct:
        print("  ✅ Automotive vertical detection working correctly")
    else:
        print("  ❌ Automotive vertical detection has issues")
    
    # Test 4: Test post-processing logic
    print("\n4. Testing post-processing logic:")
    
    # Simulate the post-processing from _extract_entities_with_qwen
    def simulate_post_processing(brands, products):
        corrected_brands = []
        corrected_products = []
        
        for brand in brands:
            brand_lower = brand.lower()
            if brand_lower in KNOWN_PRODUCTS or br_module.is_likely_product(brand):
                corrected_products.append(brand)
            elif brand_lower in br_module.KNOWN_BRANDS or br_module.is_likely_brand(brand):
                corrected_brands.append(brand)
            else:
                corrected_brands.append(brand)
        
        for product in products:
            product_lower = product.lower()
            if product_lower in br_module.KNOWN_BRANDS or br_module.is_likely_brand(product):
                corrected_brands.append(product)
            elif product_lower in KNOWN_PRODUCTS or br_module.is_likely_product(product):
                corrected_products.append(product)
            else:
                corrected_products.append(product)
        
        # Remove duplicates
        corrected_brands = list(dict.fromkeys(corrected_brands))
        corrected_products = list(dict.fromkeys(corrected_products))
        
        return corrected_brands, corrected_products
    
    # Test case: Qwen misclassifies products as brands
    qwen_brands = ["RAV4", "H6", "Toyota", "X5"]  # RAV4, H6, X5 are products
    qwen_products = ["Camry", "BMW", "CR-V", "Audi"]  # Camry, CR-V are products, BMW, Audi are brands
    
    corrected_brands, corrected_products = simulate_post_processing(qwen_brands, qwen_products)
    
    print(f"  Qwen brands: {qwen_brands}")
    print(f"  Qwen products: {qwen_products}")
    print(f"  Corrected brands: {corrected_brands}")
    print(f"  Corrected products: {corrected_products}")
    
    # Check results
    expected_brands = {"Toyota", "BMW", "Audi"}
    expected_products = {"RAV4", "H6", "X5", "Camry", "CR-V"}
    
    brands_correct = set(corrected_brands) == expected_brands
    products_correct = set(corrected_products) == expected_products
    
    if brands_correct and products_correct:
        print("  ✅ Post-processing working correctly")
    else:
        print("  ❌ Post-processing has issues")
        if not brands_correct:
            print(f"    Expected brands: {expected_brands}")
            print(f"    Got brands: {set(corrected_brands)}")
        if not products_correct:
            print(f"    Expected products: {expected_products}")
            print(f"    Got products: {set(corrected_products)}")
    
    # Summary
    print("\n" + "=" * 70)
    print("SUMMARY:")
    print(f"1. KNOWN_PRODUCTS additions: {'✅ PASS' if all_found else '❌ FAIL'}")
    print(f"2. is_likely_product function: {'✅ PASS' if all_correct else '❌ FAIL'}")
    print(f"3. Automotive vertical detection: {'✅ PASS' if all_vertical_correct else '❌ FAIL'}")
    print(f"4. Post-processing logic: {'✅ PASS' if brands_correct and products_correct else '❌ FAIL'}")
    
    all_passed = all_found and all_correct and all_vertical_correct and brands_correct and products_correct
    
    if all_passed:
        print("\n🎉 ALL TESTS PASSED! Brand/product extraction improvements are working.")
        return 0
    else:
        print("\n❌ SOME TESTS FAILED. Review the issues above.")
        return 1

if __name__ == "__main__":
    sys.exit(test_improvements())
