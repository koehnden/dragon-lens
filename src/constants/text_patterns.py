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
