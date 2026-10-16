"""MOCK profile extractor (stands in for the LLM extraction module).

Keyword rules only. Confidence values (0.9 when a keyword matched) are
ASSUMPTIONS for testing the pipeline, not model outputs.
"""

from __future__ import annotations

import hashlib
import re

from marketpulse import config
from marketpulse.contracts.models import (
    ExtractionProfile,
    FollowUpQuestion,
    ProfileField,
    ProfileFields,
)
from marketpulse.normalizers import COUNTRY_TO_CURRENCY, CURRENCY_TO_COUNTRY

_SCHOOL = ("school", "école", "ecole", "escuela", "colegio", "स्कूल", "विद्यालय")
_MARKET = ("market", "marché", "marche", "mercado", "बाजार", "बाज़ार")
_RURAL = ("village", "rural", "campagne", "pueblo", "गाँव", "गांव")
_URBAN = ("city", "town", "ville", "ciudad", "शहर")
_CITIES = (
    "delhi", "douala", "yaoundé", "yaounde", "madrid", "paris", "दिल्ली",
    "london", "new york", "tokyo", "nairobi", "berlin", "toronto", "sydney",
)
_PLACES = {  # place keyword -> (country, currency)
    ("cameroon", "cameroun", "douala", "yaoundé", "yaounde"): ("CM", "XAF"),
    ("india", "delhi", "bharat", "mumbai", "भारत", "दिल्ली"): ("IN", "INR"),
    ("spain", "españa", "espana", "madrid", "barcelona"): ("ES", "EUR"),
    ("france", "paris", "lyon"): ("FR", "EUR"),
    ("usa", "united states", "new york", "america"): ("US", "USD"),
    ("uk", "united kingdom", "london", "britain", "england"): ("GB", "GBP"),
    ("germany", "deutschland", "berlin", "munich"): ("DE", "EUR"),
    ("italy", "italia", "rome", "milan"): ("IT", "EUR"),
    ("canada", "toronto", "vancouver"): ("CA", "CAD"),
    ("australia", "sydney", "melbourne"): ("AU", "AUD"),
    ("japan", "tokyo", "osaka"): ("JP", "JPY"),
    ("kenya", "nairobi"): ("KE", "KES"),
    ("pakistan", "karachi", "lahore"): ("PK", "PKR"),
    ("ecuador", "quito"): ("EC", "USD"),
}
_CURRENCIES = (
    (("usd", "$", "dollar", "dollars"), "USD"),
    (("eur", "€", "euro", "euros"), "EUR"),
    (("gbp", "£", "pound", "pounds"), "GBP"),
    (("inr", "₹", "rupee", "rupees", "रुपये", "रुपया", "rs"), "INR"),
    (("pkr", "₨"), "PKR"),
    (("cad", "c$"), "CAD"),
    (("aud", "a$"), "AUD"),
    (("jpy", "¥", "yen"), "JPY"),
    (("kes", "shilling", "shillings", "ksh"), "KES"),
)
_QUESTIONS = {
    "en": "Which country is your shop in?",
    "fr": "Dans quel pays se trouve votre boutique ?",
    "es": "¿En qué país está su tienda?",
    "hi": "आपकी दुकान किस देश में है?",
}


def _lang(text: str, hint: str | None) -> str:
    if hint in config.SUPPORTED_LANGUAGES:
        return hint
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    low = text.lower()
    if any(w in low for w in ("boutique", "près", "marché", "école", "magasin", "ville")):
        return "fr"
    if any(w in low for w in ("tienda", "cerca", "mercado", "escuela", "ciudad")):
        return "es"
    return "en"


def _has(low: str, words: tuple[str, ...]) -> str | None:
    return next((w for w in words if w in low), None)


class MockExtractor:
    def extract_profile(
        self, description: str, language_hint: str | None = None
    ) -> ExtractionProfile:
        low = description.lower()
        lang = _lang(description, language_hint)
        anchors, ev = [], None
        for name, words in (("school", _SCHOOL), ("market", _MARKET)):
            hit = _has(low, words)
            if hit:
                anchors.append(name)
                ev = hit
        loc = (
            "rural" if _has(low, _RURAL)
            else "urban" if _has(low, _URBAN) or _has(low, _CITIES) else None
        )
        country = currency = None
        for keys, (c, cur) in _PLACES.items():
            if _has(low, keys):
                country, currency = c, cur
                break
        if not currency:
            for keys, cur in _CURRENCIES:
                if _has(low, keys):
                    currency = cur
                    break
        if not country and currency:
            country = CURRENCY_TO_COUNTRY.get(currency)
        if not currency and country:
            currency = COUNTRY_TO_CURRENCY.get(country)
        m = re.search(r"\b([12]?\d|3[01])(?:st|nd|rd|th)?\b", low)
        payday = int(m.group(1)) if m and 1 <= int(m.group(1)) <= 31 else None

        def f(value, conf=0.9, evidence=None):
            if value in (None, []):
                return ProfileField(value=None, confidence=0.0)
            return ProfileField(value=value, confidence=conf, evidence=evidence)

        fields = ProfileFields(
            location_type=f(loc, evidence=loc),
            income_band=f(None),
            payday_day=f(payday, conf=0.75),
            nearby_anchors=f(anchors, evidence=ev),
            shop_category=f(None),
            place_name=f(None),
            country=f(country),
            currency=f(currency),
        )
        questions = []
        if country is None:
            questions.append(
                FollowUpQuestion(field="country", question=_QUESTIONS[lang], reason="missing")
            )
        return ExtractionProfile(
            profile_id="prof-" + hashlib.sha1(description.encode()).hexdigest()[:8],
            language=lang,
            raw_description=description,
            fields=fields,
            follow_up_questions=questions,
        )
