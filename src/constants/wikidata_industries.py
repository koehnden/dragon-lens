PREDEFINED_INDUSTRIES = {
    "automotive": {
        "wikidata_id": "Q1420",
        "name_en": "Automotive",
        "name_zh": "汽车",
        "keywords": ["car", "suv", "automotive", "vehicle", "auto", "truck", "automobile"],
    },
    "consumer_electronics": {
        "wikidata_id": "Q5193377",
        "name_en": "Consumer Electronics",
        "name_zh": "消费电子",
        "keywords": ["smartphone", "phone", "laptop", "electronics", "tablet", "computer"],
    },
    "cosmetics": {
        "wikidata_id": "Q81783",
        "name_en": "Cosmetics",
        "name_zh": "化妆品",
        "keywords": ["cosmetics", "skincare", "beauty", "makeup", "skin care"],
    },
    "home_appliances": {
        "wikidata_id": "Q212920",
        "name_en": "Home Appliances",
        "name_zh": "家用电器",
        "keywords": ["appliance", "vacuum", "washing machine", "refrigerator", "home appliance"],
    },
    "sportswear": {
        "wikidata_id": "Q11422",
        "name_en": "Sportswear",
        "name_zh": "运动服装",
        "keywords": ["sportswear", "athletic", "shoes", "sneakers", "sports", "fitness"],
    },
    "food_beverage": {
        "wikidata_id": "Q2095",
        "name_en": "Food & Beverage",
        "name_zh": "食品饮料",
        "keywords": ["food", "beverage", "drink", "snack", "grocery"],
    },
    "luxury_goods": {
        "wikidata_id": "Q335145",
        "name_en": "Luxury Goods",
        "name_zh": "奢侈品",
        "keywords": ["luxury", "fashion", "handbag", "watch", "jewelry"],
    },
}


def find_industry_by_keyword(query: str) -> str | None:
    query_lower = query.lower()
    for industry_key, industry_data in PREDEFINED_INDUSTRIES.items():
        for keyword in industry_data["keywords"]:
            if keyword in query_lower:
                return industry_key
    return None


def get_industry_keywords(industry_key: str) -> list[str]:
    industry = PREDEFINED_INDUSTRIES.get(industry_key)
    if industry:
        return industry["keywords"]
    return []


def get_all_industry_keys() -> list[str]:
    return list(PREDEFINED_INDUSTRIES.keys())
