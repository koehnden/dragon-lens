from services.brand_recognition.consolidation_service import AnswerEntities
from services.brand_recognition.product_brand_mapping import (
    map_products_to_brands,
    parse_product_brand_mapping_response,
)


def test_map_products_to_brands_uses_list_proximity():
    answer = AnswerEntities(
        answer_id=1,
        answer_text=(
            "1. Orion Nova X2 is a solid choice.\n"
            "2. Zenith Pulse 5 delivers strong performance.\n"
            "3. Nova X2 has long range."
        ),
        raw_brands=["Orion", "Zenith"],
        raw_products=["Nova X2", "Pulse 5"],
    )

    mapping = map_products_to_brands([answer])

    assert mapping["Nova X2"] == "Orion"
    assert mapping["Pulse 5"] == "Zenith"


def test_map_products_to_brands_aggregates_across_answers():
    answer_one = AnswerEntities(
        answer_id=1,
        answer_text=(
            "1. Apex Ultra 3 is lightweight.\n"
            "2. Flux Note 8 is a premium pick."
        ),
        raw_brands=["Apex", "Flux"],
        raw_products=["Ultra 3", "Note 8"],
    )
    answer_two = AnswerEntities(
        answer_id=2,
        answer_text="Note 8 has the best camera in this segment.",
        raw_brands=["Apex", "Flux"],
        raw_products=["Ultra 3", "Note 8"],
    )

    mapping = map_products_to_brands([answer_one, answer_two])

    assert mapping["Ultra 3"] == "Apex"
    assert mapping["Note 8"] == "Flux"


def test_parse_product_brand_mapping_response_rejects_unknown_brand():
    response = """
    {
      "mappings": [
        {"product": "Nova X2", "brand": "Orion"},
        {"product": "Pulse 5", "brand": "Zenit"}
      ]
    }
    """
    products = ["Nova X2", "Pulse 5"]
    allowed_brands = {"Orion", "Zenith"}

    mapping = parse_product_brand_mapping_response(response, products, allowed_brands)

    assert mapping["Nova X2"] == "Orion"
    assert "Pulse 5" not in mapping
