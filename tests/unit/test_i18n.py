from app.i18n import SUPPORTED_UI_LOCALES, catalog_keys


def test_translation_catalogs_have_identical_keys():
    baseline = catalog_keys("zh")
    assert baseline
    for locale in SUPPORTED_UI_LOCALES:
        assert catalog_keys(locale) == baseline


def test_practice_copy_is_present_in_every_ui_catalog():
    required = {
        "nav.practice",
        "practice.title",
        "practice.kicker",
        "practice.available",
        "practice.empty",
        "practice.lead",
        "practice.question_count_one",
        "practice.question_count_many",
        "practice.browser_voice",
        "practice.voice_checking",
        "practice.voice_unsupported",
        "practice.voice_missing",
        "practice.voice_ready",
        "practice.try_again",
        "practice.start",
        "practice.play",
        "practice.replay",
        "practice.missing_word",
        "practice.missing_word_or_phrase",
        "practice.type_missing_word",
        "practice.submit",
        "practice.continue",
        "practice.correct",
        "practice.incorrect",
        "practice.your_answer",
        "practice.not_answered",
        "practice.full_sentence",
        "practice.meaning",
        "practice.session_complete",
        "practice.missed_items",
        "practice.sentence",
        "practice.again",
        "practice.back_home",
    }
    for locale in SUPPORTED_UI_LOCALES:
        assert required <= catalog_keys(locale)
