import re

LIST_PATTERNS = [
    r'^\s*\d+[.\)]\s+',
    r'^\s*\d+、',
    r'^\s*[-*]\s+',
    r'^\s*[・○→]\s*',
    r'^#{1,4}\s*\**\d+[.\)]\s*',
]

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
