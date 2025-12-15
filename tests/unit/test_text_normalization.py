from services.brand_recognition import normalize_text_for_ner


def test_normalize_fullwidth_digits():
    text = "iPhone１４ Pro"
    normalized = normalize_text_for_ner(text)
    assert normalized == "iPhone14 Pro"


def test_normalize_fullwidth_letters():
    text = "ＡＰＰＬＥ ｉＰｈｏｎｅ"
    normalized = normalize_text_for_ner(text)
    assert normalized == "APPLE iPhone"


def test_normalize_fullwidth_punctuation():
    text = "推荐品牌：Tesla（特斯拉）"
    normalized = normalize_text_for_ner(text)
    assert normalized == "推荐品牌:Tesla(特斯拉)"


def test_normalize_chinese_punctuation():
    text = "比亚迪、特斯拉、大众，都是好品牌。"
    normalized = normalize_text_for_ner(text)
    assert normalized == "比亚迪,特斯拉,大众,都是好品牌."


def test_normalize_chinese_quotes():
    text = '推荐"宋PLUS"和「理想L7」'
    normalized = normalize_text_for_ner(text)
    assert normalized == '推荐"宋PLUS"和"理想L7"'


def test_normalize_chinese_brackets():
    text = "TOP5品牌【Tesla】《比亚迪》"
    normalized = normalize_text_for_ner(text)
    assert normalized == "TOP5品牌[Tesla]<比亚迪>"


def test_normalize_whitespace():
    text = "iPhone14　Pro　　Max"
    normalized = normalize_text_for_ner(text)
    assert normalized == "iPhone14 Pro Max"


def test_normalize_mixed_spacing():
    text = "比亚迪  宋PLUS\u3000DM-i  "
    normalized = normalize_text_for_ner(text)
    assert normalized == "比亚迪 宋PLUS DM-i"


def test_normalize_complex_text():
    text = """
    推荐TOP　５：
    １。Ｔｅｓｌａ　Ｍｏｄｅｌ　Ｙ　－　性能优秀，续航里程长。
    ２。比亚迪「宋ＰＬＵＳ」－　性价比高、舒适性好！
    """
    normalized = normalize_text_for_ner(text)

    assert "Tesla" in normalized
    assert "Model" in normalized
    assert "PLUS" in normalized
    assert "１" not in normalized
    assert "Ｔｅｓｌａ" not in normalized
    assert "　" not in normalized


def test_normalize_empty_text():
    assert normalize_text_for_ner("") == ""
    assert normalize_text_for_ner(None) is None


def test_normalize_preserves_chinese_chars():
    text = "比亚迪宋PLUS很受欢迎"
    normalized = normalize_text_for_ner(text)
    assert "比亚迪" in normalized
    assert "宋" in normalized
    assert "受欢迎" in normalized


def test_normalize_preserves_brand_case():
    text = "iPhone14和Samsung S23都很好"
    normalized = normalize_text_for_ner(text)
    assert "iPhone14" in normalized
    assert "Samsung" in normalized


def test_normalize_number_letter_combo():
    text = "小米１３　Ｕｌｔｒａ"
    normalized = normalize_text_for_ner(text)
    assert normalized == "小米13 Ultra"


def test_normalize_product_with_dash():
    text = "宋ＰＬＵＳ　ＤＭ－ｉ"
    normalized = normalize_text_for_ner(text)
    assert "PLUS" in normalized
    assert "DM-i" in normalized
