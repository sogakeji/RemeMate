"""Product language boundaries.

The product UI, AI features, and reader intentionally have different
language sets.  ``KNOWN_LANGUAGE_NAMES`` keeps legacy vocabulary data
readable while the narrower maps are used for new user-facing choices.
"""

AI_LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "英语",
    "fr": "法语",
    "ja": "日语",
    "ko": "韩语",
    "es": "西班牙语",
}

LEGACY_LANGUAGE_NAMES = {
    "de": "德语",
    "ru": "俄语",
}

KNOWN_LANGUAGE_NAMES = {
    **AI_LANGUAGE_NAMES,
    **LEGACY_LANGUAGE_NAMES,
}

READER_LANGUAGE_NAMES = {
    "zh": "中文",
    "en": "英语",
    "fr": "法语",
    "ja": "日语",
}
