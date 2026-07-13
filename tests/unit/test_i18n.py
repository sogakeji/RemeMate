from app.i18n import SUPPORTED_UI_LOCALES, catalog_keys


def test_translation_catalogs_have_identical_keys():
    baseline = catalog_keys("zh")
    assert baseline
    for locale in SUPPORTED_UI_LOCALES:
        assert catalog_keys(locale) == baseline
