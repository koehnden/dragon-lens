import re

LIST_PATTERNS = [
    r'^\s*\d+[\.．\)）]\s+',
    r'^\s*\d+、',
    r'^\s*[-*•·]\s+',
    r'^\s*[・○→]\s*',
    r'^#{1,4}\s*\**\d+[\.．\)）]\s*',
]

NUMBERED_LIST_MARKER_CHARS = r"\.．\)）"
BULLET_MARKER_CLASS = r"\-\*•·"
ASIAN_BULLET_MARKER_CLASS = r"・○→"
LIST_ITEM_MARKER_REGEX = (
    rf"(?:^\s*\d+[{NUMBERED_LIST_MARKER_CHARS}]|^\s*\d+、|^\s*[{BULLET_MARKER_CLASS}]|^\s*[{ASIAN_BULLET_MARKER_CLASS}]|^#{{1,4}}\s*\**\d+[{NUMBERED_LIST_MARKER_CHARS}])"
)
LIST_ITEM_SPLIT_REGEX = LIST_ITEM_MARKER_REGEX + r"\s*"

TOP_LEVEL_INDENT_RE = r"[ \t]*"
TOP_LEVEL_LIST_ITEM_MARKER_REGEX = (
    rf"(?:^{TOP_LEVEL_INDENT_RE}\d+[{NUMBERED_LIST_MARKER_CHARS}]|^{TOP_LEVEL_INDENT_RE}\d+、|^{TOP_LEVEL_INDENT_RE}[{BULLET_MARKER_CLASS}]|^{TOP_LEVEL_INDENT_RE}[{ASIAN_BULLET_MARKER_CLASS}]|^#{{1,4}}\s*\**\d+[{NUMBERED_LIST_MARKER_CHARS}])"
)
TOP_LEVEL_LIST_ITEM_SPLIT_REGEX = TOP_LEVEL_LIST_ITEM_MARKER_REGEX + r"\s*"

COMPILED_LIST_PATTERNS = [re.compile(p, re.MULTILINE) for p in LIST_PATTERNS]

COMPARISON_MARKERS = [
    "similar to", "comparable to", "like ", "better than", "worse than",
    "competing with", "compared to", "versus", " vs ", " vs.",
    "outperforming", "ahead of", "behind ",
    "类似于", "相比于", "胜过", "不如", "优于", "竞争对手",
    "，比", "，和", "，与", "，类似", "，相比",
]

CLAUSE_SEPARATORS = [". ", ", ", "; ", "。", "，", "；", " - "]

VALID_EXTRA_TERMS = {"hybrid", "ev", "plus", "pro", "max", "ultra", "mini", "dmi", "dm-i", "dmp", "dm-p"}

# Expected count patterns - extract number from LLM output phrases
EXPECTED_COUNT_PATTERNS = [
    # English patterns
    r"(?i)\bTOP\s*(\d+)\b",                    # TOP 10, Top10, top 5
    r"(?i)\btop[-\s]*(\d+)\b",                 # top-10, top 10
    r"(?i)\bbest\s+(\d+)\b",                   # best 10
    r"(?i)\b(\d+)\s+best\b",                   # 10 best
    r"(?i)\b(\d+)\s+top\b",                    # 10 top

    # Chinese patterns
    r"推荐(\d+)款",                             # 推荐10款
    r"(\d+)大推荐",                             # 10大推荐
    r"前(\d+)名",                               # 前10名
    r"TOP\s*(\d+)",                             # TOP10 in Chinese text
    r"(\d+)款推荐",                             # 10款推荐
    r"(\d+)个推荐",                             # 10个推荐
    r"排名前(\d+)",                             # 排名前10
    r"(\d+)强",                                 # 10强
]

# Chinese number mapping for "十大品牌" style patterns
CHINESE_NUMBERS = {
    "一": 1, "二": 2, "三": 3, "四": 4, "五": 5,
    "六": 6, "七": 7, "八": 8, "九": 9, "十": 10,
    "十一": 11, "十二": 12, "十五": 15, "二十": 20,
}

CHINESE_COUNT_PATTERNS = [
    r"([一二三四五六七八九十]+)大品牌",          # 十大品牌
    r"([一二三四五六七八九十]+)大推荐",          # 十大推荐
    r"([一二三四五六七八九十]+)款推荐",          # 十款推荐
]

COMPILED_EXPECTED_COUNT_PATTERNS = [re.compile(p) for p in EXPECTED_COUNT_PATTERNS]
COMPILED_CHINESE_COUNT_PATTERNS = [re.compile(p) for p in CHINESE_COUNT_PATTERNS]
