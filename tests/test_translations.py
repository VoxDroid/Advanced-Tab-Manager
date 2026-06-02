from advancedtabmanager import translations
from advancedtabmanager.translations import en, fil, ja, ko, zh


def test_translation_modules_loaded():
    assert hasattr(translations, "__doc__")


def test_translation_key_subset_present():
    required_keys = {
        "app_name",
        "tab_main",
        "tab_settings",
        "browser_chrome",
        "theme_dark_navy",
    }

    all_translations = [
        en.translations,
        ja.translations,
        ko.translations,
        zh.translations,
        fil.translations,
    ]

    for data in all_translations:
        missing = required_keys - data.keys()
        assert not missing
