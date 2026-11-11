"""Languages of UniBridge and the fixed texts (answers, handoff, scholarship guide, demo UI) in each of them.

The language list covers the languages most international students in Italy read best; adding one is one entry
in each table below plus a run of scripts/translate_i18n.py.

Texts: Italian, English and Arabic are written by hand where they are used (`localize(key, {"it": .., "en": ..,
"ar": ..})`). The other languages come from src/p14_search/i18n_llm.json, translated from English by the LLM
once (temperature 0) and flagged llm_generated / needs_native_review. A text missing there falls back to English,
so a new key never breaks the service before the file is regenerated.
"""

from __future__ import annotations

import json
from pathlib import Path

LANGS = ("it", "en", "ar", "fr", "es", "pt", "de", "ro", "sq", "uk", "ru", "tr", "fa", "ur", "hi", "bn", "zh")
HAND_WRITTEN = ("it", "en", "ar")
RTL = frozenset({"ar", "fa", "ur"})
# English names, used in the LLM prompts
NAMES = {"it": "Italian", "en": "English", "ar": "Arabic", "fr": "French", "es": "Spanish", "pt": "Portuguese",
         "de": "German", "ro": "Romanian", "sq": "Albanian", "uk": "Ukrainian", "ru": "Russian", "tr": "Turkish",
         "fa": "Persian", "ur": "Urdu", "hi": "Hindi", "bn": "Bengali", "zh": "Simplified Chinese"}
# Italian names, used in the e-mail drafts to the offices
NAMES_IT = {"it": "italiano", "en": "inglese", "ar": "arabo", "fr": "francese", "es": "spagnolo", "pt": "portoghese",
            "de": "tedesco", "ro": "rumeno", "sq": "albanese", "uk": "ucraino", "ru": "russo", "tr": "turco",
            "fa": "persiano", "ur": "urdu", "hi": "hindi", "bn": "bengalese", "zh": "cinese"}
# Own names, shown in the language selector of the UI
NATIVE = {"it": "Italiano", "en": "English", "ar": "العربية", "fr": "Français", "es": "Español", "pt": "Português",
          "de": "Deutsch", "ro": "Română", "sq": "Shqip", "uk": "Українська", "ru": "Русский", "tr": "Türkçe",
          "fa": "فارسی", "ur": "اردو", "hi": "हिन्दी", "bn": "বাংলা", "zh": "中文"}

GENERATED_PATH = Path(__file__).with_name("i18n_llm.json")
SOURCES: dict[str, dict[str, str]] = {}  # key -> hand-written texts of every localized text (read by scripts/translate_i18n.py)


def _generated() -> dict[str, dict[str, str]]:
    if not GENERATED_PATH.exists():
        return {}
    return json.loads(GENERATED_PATH.read_text(encoding="utf-8"))["texts"]


_GENERATED = _generated()


def localize(key: str, texts: dict[str, str]) -> dict[str, str]:
    """The text in every language of LANGS: hand-written if given, else the generated translation, else English."""
    SOURCES[key] = dict(texts)
    return {lang: texts.get(lang) or _GENERATED.get(lang, {}).get(key) or texts["en"] for lang in LANGS}
