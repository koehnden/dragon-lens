import logging
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

WIKIDATA_SPARQL_ENDPOINT = "https://query.wikidata.org/sparql"
REQUEST_TIMEOUT = 60
RATE_LIMIT_DELAY = 1.5


def _execute_sparql_query(query: str, retries: int = 3) -> list[dict[str, Any]]:
    headers = {
        "Accept": "application/sparql-results+json",
        "User-Agent": "DragonLens/1.0 (https://github.com/example/dragonlens)",
    }

    for attempt in range(retries):
        try:
            time.sleep(RATE_LIMIT_DELAY)

            with httpx.Client(timeout=REQUEST_TIMEOUT) as client:
                response = client.get(
                    WIKIDATA_SPARQL_ENDPOINT,
                    params={"query": query, "format": "json"},
                    headers=headers,
                )

            if response.status_code == 429:
                wait_time = (attempt + 1) * 5
                logger.warning(f"Rate limited, waiting {wait_time}s before retry")
                time.sleep(wait_time)
                continue

            response.raise_for_status()
            data = response.json()
            return data.get("results", {}).get("bindings", [])

        except httpx.TimeoutException:
            logger.warning(f"SPARQL query timeout (attempt {attempt + 1}/{retries})")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue

        except Exception as e:
            logger.error(f"SPARQL query failed: {e}")
            if attempt < retries - 1:
                time.sleep(2 ** attempt)
            continue

    return []


def query_brands_for_industry(industry_wikidata_id: str) -> list[dict]:
    query = f"""
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {{
      ?brand wdt:P31/wdt:P279* wd:Q4830453 .
      ?brand wdt:P452 wd:{industry_wikidata_id} .

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }}

      OPTIONAL {{
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }}

      OPTIONAL {{
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }}

      OPTIONAL {{
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }}
    }}
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 3000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def query_automobile_manufacturers() -> list[dict]:
    query = """
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {
      ?brand wdt:P31/wdt:P279* wd:Q786820 .

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }

      OPTIONAL {
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }
    }
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 3000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def query_automobile_models() -> list[dict]:
    query = """
    SELECT DISTINCT ?model ?modelLabel ?modelLabelZh ?manufacturer ?manufacturerLabel
    WHERE {
      ?model wdt:P31/wdt:P279* wd:Q3231690 .
      ?model wdt:P176 ?manufacturer .

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?model rdfs:label ?modelLabel .
        ?manufacturer rdfs:label ?manufacturerLabel .
      }

      OPTIONAL {
        ?model rdfs:label ?modelLabelZh .
        FILTER(LANG(?modelLabelZh) = "zh")
      }
    }
    LIMIT 5000
    """

    results = _execute_sparql_query(query)
    return _parse_product_results(results)


def query_products_for_brand(brand_wikidata_id: str) -> list[dict]:
    query = f"""
    SELECT DISTINCT ?product ?productLabel ?productLabelZh
    WHERE {{
      ?product wdt:P176 wd:{brand_wikidata_id} .

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en" .
        ?product rdfs:label ?productLabel .
      }}

      OPTIONAL {{
        ?product rdfs:label ?productLabelZh .
        FILTER(LANG(?productLabelZh) = "zh")
      }}
    }}
    LIMIT 500
    """

    results = _execute_sparql_query(query)
    return _parse_product_results(results, brand_wikidata_id)


def query_smartphone_brands() -> list[dict]:
    query = """
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {
      ?brand wdt:P31/wdt:P279* wd:Q18388277 .

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }

      OPTIONAL {
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }
    }
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 3000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def query_cosmetics_brands() -> list[dict]:
    query = """
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {
      ?brand wdt:P31/wdt:P279* wd:Q1058914 .

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }

      OPTIONAL {
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }
    }
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 3000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def query_sportswear_brands() -> list[dict]:
    query = """
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {
      ?brand wdt:P31/wdt:P279* wd:Q2416217 .

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }

      OPTIONAL {
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }
    }
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 3000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def query_luxury_brands() -> list[dict]:
    query = """
    SELECT DISTINCT ?brand ?brandLabel ?brandLabelZh
           (GROUP_CONCAT(DISTINCT ?aliasEn; separator="|") AS ?aliasesEn)
           (GROUP_CONCAT(DISTINCT ?aliasZh; separator="|") AS ?aliasesZh)
    WHERE {
      {
        ?brand wdt:P31/wdt:P279* wd:Q15243209 .
      } UNION {
        ?brand wdt:P31/wdt:P279* wd:Q1057954 .
      }

      SERVICE wikibase:label {
        bd:serviceParam wikibase:language "en" .
        ?brand rdfs:label ?brandLabel .
      }

      OPTIONAL {
        ?brand rdfs:label ?brandLabelZh .
        FILTER(LANG(?brandLabelZh) = "zh")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasEn .
        FILTER(LANG(?aliasEn) = "en")
      }

      OPTIONAL {
        ?brand skos:altLabel ?aliasZh .
        FILTER(LANG(?aliasZh) = "zh")
      }
    }
    GROUP BY ?brand ?brandLabel ?brandLabelZh
    LIMIT 5000
    """

    results = _execute_sparql_query(query)
    return _parse_brand_results(results)


def search_industries(search_term: str) -> list[dict]:
    query = f"""
    SELECT DISTINCT ?industry ?industryLabel ?industryDescription
    WHERE {{
      ?industry wdt:P31/wdt:P279* wd:Q8148 .
      ?industry rdfs:label ?label .
      FILTER(CONTAINS(LCASE(?label), LCASE("{search_term}")))
      FILTER(LANG(?label) = "en")

      SERVICE wikibase:label {{
        bd:serviceParam wikibase:language "en" .
        ?industry rdfs:label ?industryLabel .
        ?industry schema:description ?industryDescription .
      }}
    }}
    LIMIT 20
    """

    results = _execute_sparql_query(query)

    industries = []
    for result in results:
        wikidata_id = result.get("industry", {}).get("value", "").split("/")[-1]
        industries.append({
            "wikidata_id": wikidata_id,
            "name_en": result.get("industryLabel", {}).get("value", ""),
            "description": result.get("industryDescription", {}).get("value", ""),
        })

    return industries


def _parse_brand_results(results: list[dict]) -> list[dict]:
    brands = []
    for result in results:
        wikidata_id = result.get("brand", {}).get("value", "").split("/")[-1]
        aliases_en = result.get("aliasesEn", {}).get("value", "")
        aliases_zh = result.get("aliasesZh", {}).get("value", "")

        brands.append({
            "wikidata_id": wikidata_id,
            "name_en": result.get("brandLabel", {}).get("value", ""),
            "name_zh": result.get("brandLabelZh", {}).get("value", ""),
            "aliases_en": aliases_en.split("|") if aliases_en else [],
            "aliases_zh": aliases_zh.split("|") if aliases_zh else [],
            "entity_type": "brand",
        })

    return brands


def _parse_product_results(results: list[dict], parent_brand_id: str = None) -> list[dict]:
    products = []
    for result in results:
        if "model" in result:
            wikidata_id = result.get("model", {}).get("value", "").split("/")[-1]
            name_en = result.get("modelLabel", {}).get("value", "")
            name_zh = result.get("modelLabelZh", {}).get("value", "")
            manufacturer_id = result.get("manufacturer", {}).get("value", "").split("/")[-1]
        else:
            wikidata_id = result.get("product", {}).get("value", "").split("/")[-1]
            name_en = result.get("productLabel", {}).get("value", "")
            name_zh = result.get("productLabelZh", {}).get("value", "")
            manufacturer_id = parent_brand_id

        products.append({
            "wikidata_id": wikidata_id,
            "name_en": name_en,
            "name_zh": name_zh,
            "parent_brand_wikidata_id": manufacturer_id,
            "entity_type": "product",
        })

    return products
