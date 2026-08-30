from app.services.practice import (
    PRACTICE_LANGUAGES,
    normalize_answer,
    prompt_parts,
    target_occurs_uniquely,
    voice_locale,
)


def test_prompt_parts_maps_casefold_expansion_back_to_nfc_source():
    before, after = prompt_parts("ß cible", "cible")

    assert before == "ß "
    assert after == ""


def test_prompt_parts_splits_japanese_on_unique_substring():
    before, after = prompt_parts("今日は学校に行きます。", "学校", "ja")

    assert before == "今日は"
    assert after == "に行きます。"


def test_prompt_parts_splits_chinese_on_unique_substring():
    before, after = prompt_parts("今天我去学校上课。", "学校", "zh")

    assert before == "今天我去"
    assert after == "上课。"


def test_prompt_parts_does_not_cloze_repeated_chinese_substring():
    sentence = "学校的附近还有一所学校。"
    before, after = prompt_parts(sentence, "学校", "zh")

    assert before == sentence
    assert after == ""


def test_prompt_parts_rejects_obvious_chinese_true_substring():
    sentence = "今天我去学校上课。"
    before, after = prompt_parts(sentence, "校", "zh")

    assert before == sentence
    assert after == ""


def test_prompt_parts_does_not_cloze_repeated_japanese_substring():
    sentence = "学校の近くに別の学校があります。"
    before, after = prompt_parts(sentence, "学校", "ja")

    assert before == sentence
    assert after == ""


def test_prompt_parts_keeps_french_boundaries_in_unspaced_japanese_text():
    sentence = "今日は学校に行きます。"
    before, after = prompt_parts(sentence, "学校")

    assert before == sentence
    assert after == ""


def test_japanese_unique_substring_counts_as_one_occurrence():
    assert target_occurs_uniquely("今日は学校に行きます。", "学校", "ja") is True
    assert target_occurs_uniquely("学校の近くに別の学校があります。", "学校", "ja") is False


def test_chinese_unique_substring_counts_as_one_occurrence():
    assert target_occurs_uniquely("今天我去学校上课。", "学校", "zh") is True
    assert target_occurs_uniquely("学校的附近还有一所学校。", "学校", "zh") is False
    assert target_occurs_uniquely("今天我去学校上课。", "校", "zh") is False


def test_practice_languages_include_chinese():
    assert "zh" in PRACTICE_LANGUAGES
    assert "ja" in PRACTICE_LANGUAGES
    assert "fr" in PRACTICE_LANGUAGES


def test_japanese_normalize_folds_halfwidth_katakana():
    assert normalize_answer("ｺｰﾋｰ", "ja") == "コーヒー"


def test_chinese_normalize_folds_fullwidth_ascii():
    assert normalize_answer("３Ａ", "zh") == "3A"


def test_chinese_normalize_strips_whitespace():
    assert normalize_answer("　学校 ", "zh") == "学校"


def test_chinese_normalize_strips_punctuation():
    assert normalize_answer("「学校」。", "zh") == "学校"
    assert normalize_answer("学校，", "zh") == "学校"


def test_chinese_normalize_does_not_accept_pinyin_or_variants():
    assert normalize_answer("xuexiao", "zh") != normalize_answer("学校", "zh")
    assert normalize_answer("xuéxiào", "zh") != normalize_answer("学校", "zh")
    assert normalize_answer("學校", "zh") != normalize_answer("学校", "zh")
    assert normalize_answer("花儿", "zh") != normalize_answer("花", "zh")
    assert normalize_answer("三", "zh") != normalize_answer("3", "zh")


def test_chinese_normalize_treats_punctuation_only_as_empty():
    assert normalize_answer("。", "zh") == ""
    assert normalize_answer("   ", "zh") == ""


def test_japanese_normalize_strips_whitespace():
    assert normalize_answer("　コーヒー ", "ja") == "コーヒー"


def test_japanese_normalize_strips_punctuation_but_keeps_choonpu():
    assert normalize_answer("「コーヒー」。", "ja") == "コーヒー"


def test_voice_locale_uses_bcp47_defaults():
    assert voice_locale("ja") == "ja-JP"
    assert voice_locale("fr") == "fr-FR"


def test_japanese_normalize_does_not_loosen_script_or_mora():
    assert normalize_answer("がっこう", "ja") != normalize_answer("学校", "ja")
    assert normalize_answer("ゲーム", "ja") != normalize_answer("げーむ", "ja")
    assert normalize_answer("がつこう", "ja") != normalize_answer("がっこう", "ja")
    assert normalize_answer("きや", "ja") != normalize_answer("きゃ", "ja")
    assert normalize_answer("こうひい", "ja") != normalize_answer("コーヒー", "ja")
