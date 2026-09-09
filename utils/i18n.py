"""Internationalisation — session-based language with IP detection.

CarHero supports 12 languages:
en (English), et (Estonian), de (German), fr (French), sv (Swedish),
lv (Latvian), no (Norwegian), da (Danish), pl (Polish),
nl (Dutch), fi (Finnish), lt (Lithuanian).
"""

from __future__ import annotations

from typing import Any

DEFAULT_LANG = "en"

LANGUAGES: dict[str, dict] = {
    "en": {"name": "English",    "native": "English",    "flag": "\U0001f1ec\U0001f1e7"},
    "et": {"name": "Estonian",   "native": "Eesti",      "flag": "\U0001f1ea\U0001f1ea"},
    "de": {"name": "German",     "native": "Deutsch",    "flag": "\U0001f1e9\U0001f1ea"},
    "fr": {"name": "French",     "native": "Français", "flag": "\U0001f1eb\U0001f1f7"},
    "sv": {"name": "Swedish",    "native": "Svenska",    "flag": "\U0001f1f8\U0001f1ea"},
    "lv": {"name": "Latvian",    "native": "Latviešu", "flag": "\U0001f1f1\U0001f1fb"},
    "no": {"name": "Norwegian",  "native": "Norsk",      "flag": "\U0001f1f3\U0001f1f4"},
    "da": {"name": "Danish",     "native": "Dansk",      "flag": "\U0001f1e9\U0001f1f0"},
    "pl": {"name": "Polish",     "native": "Polski",     "flag": "\U0001f1f5\U0001f1f1"},
    "nl": {"name": "Dutch",      "native": "Nederlands", "flag": "\U0001f1f3\U0001f1f1"},
    "fi": {"name": "Finnish",    "native": "Suomi",      "flag": "\U0001f1eb\U0001f1ee"},
    "lt": {"name": "Lithuanian", "native": "Lietuvių",  "flag": "\U0001f1f1\U0001f1f9"},
}

SUPPORTED_LANGS = set(LANGUAGES.keys())

_ESTONIAN_IP_PREFIXES = (
    "85.253.", "90.190.", "84.50.", "213.168.", "195.50.",
    "62.65.", "88.196.", "86.43.", "193.40.", "194.126.",
)
_LATVIAN_IP_PREFIXES = (
    "195.13.", "213.175.", "195.122.", "80.233.", "78.84.",
)


def _get_client_ip(request) -> str:
    forwarded = (getattr(request, "headers", {}) or {}).get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    client = getattr(request, "client", None)
    return client.host if client else ""


def detect_language(request) -> str:
    ip = _get_client_ip(request)
    if any(ip.startswith(p) for p in _ESTONIAN_IP_PREFIXES):
        return "et"
    if any(ip.startswith(p) for p in _LATVIAN_IP_PREFIXES):
        return "lv"
    return DEFAULT_LANG


def get_lang(sess: dict[str, Any], request=None) -> str:
    lang = (sess.get("lang") or "").lower()
    if lang in SUPPORTED_LANGS:
        return lang
    if request:
        detected = detect_language(request)
        sess["lang"] = detected
        return detected
    return DEFAULT_LANG


def set_lang(sess: dict[str, Any], lang: str) -> str:
    code = (lang or "").lower()
    if code in SUPPORTED_LANGS:
        sess["lang"] = code
    return get_lang(sess)


def t(key: str, lang: str = DEFAULT_LANG) -> str:
    entry = TRANSLATIONS.get(key)
    if not entry:
        return key
    return entry.get(lang, entry.get("en", key))


def agent_t(slug: str, field: str, lang: str = DEFAULT_LANG) -> str:
    entry = AGENT_TRANSLATIONS.get(slug, {}).get(field)
    if not entry:
        return slug if field == "name" else ""
    return entry.get(lang, entry.get("en", slug))


def category_t(key: str, field: str, lang: str = DEFAULT_LANG) -> str:
    entry = CATEGORY_TRANSLATIONS.get(key, {}).get(field)
    if not entry:
        return key if field == "name" else ""
    return entry.get(lang, entry.get("en", key))


def js_translations(lang: str = DEFAULT_LANG) -> dict[str, str]:
    return {k.removeprefix("js_"): t(k, lang)
            for k in TRANSLATIONS if k.startswith("js_")}


# ---------------------------------------------------------------------------
# Translation catalog
# ---------------------------------------------------------------------------

TRANSLATIONS: dict[str, dict[str, str]] = {

    # -- Navigation --
    "nav_home": {
        "en": "Home", "et": "Avaleht", "de": "Startseite",
        "fr": "Accueil", "sv": "Hem", "lv": "Sākums",
        "no": "Hjem", "da": "Hjem", "pl": "Strona główna",
        "nl": "Home", "fi": "Etusivu", "lt": "Pradžia",
    },
    "nav_advisory": {
        "en": "Advisory", "et": "Nõustamine", "de": "Beratung",
        "fr": "Conseil", "sv": "Rådgivning", "lv": "Konsultācijas",
        "no": "Rådgivning", "da": "Rådgivning", "pl": "Doradztwo",
        "nl": "Advies", "fi": "Neuvonta", "lt": "Konsultacijos",
    },
    "nav_browse": {
        "en": "Browse", "et": "Sirvi", "de": "Durchsuchen",
        "fr": "Parcourir", "sv": "Bläddra", "lv": "Pārlūkot",
        "no": "Bla gjennom", "da": "Gennemse", "pl": "Przeglądaj",
        "nl": "Bladeren", "fi": "Selaa", "lt": "Naršyti",
    },
    "nav_about": {
        "en": "About", "et": "Meist", "de": "Über uns",
        "fr": "À propos", "sv": "Om oss", "lv": "Par mums",
        "no": "Om oss", "da": "Om os", "pl": "O nas",
        "nl": "Over ons", "fi": "Tietoa", "lt": "Apie mus",
    },
    "nav_market_map": {
        "en": "Market Map", "et": "Turukaart", "de": "Marktkarte",
        "fr": "Carte du marché", "sv": "Marknadskarta", "lv": "Tirgus karte",
        "no": "Markedskart", "da": "Markedskort", "pl": "Mapa rynku",
        "nl": "Marktkaart", "fi": "Markkina­kartta", "lt": "Rinkos žemėlapis",
    },
    "nav_contact": {
        "en": "Contact", "et": "Kontakt", "de": "Kontakt",
        "fr": "Contact", "sv": "Kontakt", "lv": "Kontakti",
        "no": "Kontakt", "da": "Kontakt", "pl": "Kontakt",
        "nl": "Contact", "fi": "Yhteystiedot", "lt": "Kontaktai",
    },
    "nav_open_app": {
        "en": "Sign In", "et": "Logi sisse", "de": "Anmelden",
        "fr": "Se connecter", "sv": "Logga in", "lv": "Pierakstīties",
        "no": "Logg inn", "da": "Log ind", "pl": "Zaloguj się",
        "nl": "Inloggen", "fi": "Kirjaudu", "lt": "Prisijungti",
    },
    "nav_login": {
        "en": "Login", "et": "Logi sisse", "de": "Anmelden",
        "fr": "Connexion", "sv": "Logga in", "lv": "Pieslēgties",
        "no": "Logg inn", "da": "Log ind", "pl": "Zaloguj się",
        "nl": "Inloggen", "fi": "Kirjaudu sisään", "lt": "Prisijungti",
    },
    "nav_logout": {
        "en": "Log Out", "et": "Logi välja", "de": "Abmelden",
        "fr": "Déconnexion", "sv": "Logga ut", "lv": "Iziet",
        "no": "Logg ut", "da": "Log ud", "pl": "Wyloguj się",
        "nl": "Uitloggen", "fi": "Kirjaudu ulos", "lt": "Atsijungti",
    },

    # -- Hero --
    "hero_h1": {
        "en": "Your AI Car Advisor.",
        "et": "Sinu tehisintellektist autonõustaja.",
        "de": "Ihr KI-Autoberater.",
        "fr": "Votre conseiller automobile IA.",
        "sv": "Din AI-bilrådgivare.",
        "lv": "Jūsu AI auto konsultants.",
        "no": "Din AI-bilrådgiver.",
        "da": "Din AI-bilrådgiver.",
        "pl": "Twój doradca samochodowy AI.",
        "nl": "Uw AI-autoadviseur.",
        "fi": "Tekoäly-autoneuvojasi.",
        "lt": "Jūsų AI automobilių patarėjas.",
    },
    "hero_h2": {
        "en": "Search, compare, and value premium cars across Europe.",
        "et": "Otsi, võrdle ja hinda premium autosid üle Euroopa.",
        "de": "Suchen, vergleichen und bewerten Sie Premium-Autos in ganz Europa.",
        "fr": "Recherchez, comparez et évaluez des voitures premium en Europe.",
        "sv": "Sök, jämför och värdera premiumbilar i hela Europa.",
        "lv": "Meklējiet, salīziniet un novērtējiet premium automašīnas visā Eiropā.",
        "no": "Søk, sammenlign og verdivurder premiumbiler i hele Europa.",
        "da": "Søg, sammenlign og vurder premiumbiler i hele Europa.",
        "pl": "Szukaj, porównuj i wyceniaj samochody premium w całej Europie.",
        "nl": "Zoek, vergelijk en waardeer premiumauto's in heel Europa.",
        "fi": "Etsi, vertaa ja arvota premium-autoja koko Euroopassa.",
        "lt": "Ieškokite, lyginkite ir vertinkite premium automobilius visoje Europoje.",
    },
    "hero_body": {
        "en": "AI-powered car advisory combining market intelligence, price analytics, and valuation tools. From BMW to Porsche, across UK, Germany, and the EU.",
        "et": "Tehisintellektil põhinev autonõustamine, mis ühendab turuluure, hinnaanalüütika ja hindamisvahendid. BMW-st Porscheni, ÜK-st Saksamaa ja EL-ini.",
        "de": "KI-gestützte Autoberatung mit Marktintelligenz, Preisanalysen und Bewertungstools. Von BMW bis Porsche, in UK, Deutschland und der EU.",
        "fr": "Conseil automobile propulsé par l'IA combinant intelligence de marché, analyse de prix et outils d'évaluation. De BMW à Porsche, au Royaume-Uni, en Allemagne et dans l'UE.",
        "sv": "AI-driven bilrådgivning som kombinerar marknadsintelligens, prisanalys och värderingsverktyg. Från BMW till Porsche, i UK, Tyskland och EU.",
        "lv": "AI auto konsultācijas, kas apvieno tirgus izlūkošanu, cenu analītiku un vērtēšanas rīkus.",
        "no": "AI-drevet bilrådgivning som kombinerer markedsintelligens, prisanalyse og verdsettelsesverktøy.",
        "da": "AI-drevet bilrådgivning der kombinerer markedsintelligens, prisanalyse og værdiansættelsesværktøjer.",
        "pl": "Doradztwo samochodowe wspierane przez AI łączące analizę rynku, analitykę cenową i narzędzia wyceny.",
        "nl": "AI-gestuurd autoadvies dat marktintelligentie, prijsanalyse en waarderingstools combineert.",
        "fi": "Tekoälypohjainen autoneuvonta yhdistää markkinatiedon, hinta-analytiikan ja arvostustyökalut.",
        "lt": "Dirbtinio intelekto valdomas automobilių konsultavimas, jungiantis rinkos žvalgybą, kainų analitiką ir vertinimo įrankius.",
    },
    "hero_cta_start": {
        "en": "Sign In", "et": "Logi sisse",
        "de": "Anmelden", "fr": "Se connecter",
        "sv": "Logga in", "lv": "Pierakstīties",
        "no": "Logg inn", "da": "Log ind",
        "pl": "Zaloguj się", "nl": "Inloggen",
        "fi": "Kirjaudu", "lt": "Prisijungti",
    },
    "hero_cta_explore": {
        "en": "Explore Market", "et": "Avasta turg",
        "de": "Markt erkunden", "fr": "Explorer le marché",
        "sv": "Utforska marknaden", "lv": "Izpētīt tirgu",
        "no": "Utforsk markedet", "da": "Udforsk markedet",
        "pl": "Odkryj rynek", "nl": "Markt verkennen",
        "fi": "Tutustu markkinoihin", "lt": "Naršyti rinką",
    },

    # -- Stats --
    "stat_listings": {
        "en": "Car Listings", "et": "Autokuulutused", "de": "Fahrzeugangebote",
        "fr": "Annonces", "sv": "Bilannonser", "lv": "Auto sludinājumi",
        "no": "Bilannonser", "da": "Bilannoncer", "pl": "Ogłoszenia",
        "nl": "Autoadvertenties", "fi": "Autoilmoitukset", "lt": "Skelbimai",
    },
    "stat_brands": {
        "en": "Premium Brands", "et": "Premium brändid", "de": "Premiummarken",
        "fr": "Marques premium", "sv": "Premiummärken", "lv": "Premium zīmoli",
        "no": "Premiummerker", "da": "Premiummærker", "pl": "Marki premium",
        "nl": "Premiummerken", "fi": "Premium-merkit", "lt": "Premium prekės ženklai",
    },
    "stat_countries": {
        "en": "Countries", "et": "Riigid", "de": "Länder",
        "fr": "Pays", "sv": "Länder", "lv": "Valstis",
        "no": "Land", "da": "Lande", "pl": "Kraje",
        "nl": "Landen", "fi": "Maat", "lt": "Šalys",
    },
    "stat_sources": {
        "en": "Data Sources", "et": "Andmeallikad", "de": "Datenquellen",
        "fr": "Sources de données", "sv": "Datakällor", "lv": "Datu avoti",
        "no": "Datakilder", "da": "Datakilder", "pl": "Źródła danych",
        "nl": "Databronnen", "fi": "Tietolähteet", "lt": "Duomenų šaltiniai",
    },

    # -- Features --
    "feat_advisory": {
        "en": "Car Advisory", "et": "Autonõustamine", "de": "Autoberatung",
        "fr": "Conseil automobile", "sv": "Bilrådgivning", "lv": "Auto konsultācijas",
        "no": "Bilrådgivning", "da": "Bilrådgivning", "pl": "Doradztwo samochodowe",
        "nl": "Autoadvies", "fi": "Autoneuvonta", "lt": "Automobilių konsultacijos",
    },
    "feat_advisory_body": {
        "en": "AI-powered recommendations from 5 specialist agents. Search listings, compare models, get valuations, and receive buying advice tailored to your needs.",
        "et": "Tehisintellekti soovitused 5 erialagendilt. Otsi kuulutusi, võrdle mudeleid, saa hindamisi ja omandamisnõu.",
        "de": "KI-gestützte Empfehlungen von 5 Spezialagenten. Suchen Sie Angebote, vergleichen Sie Modelle und erhalten Sie Kaufberatung.",
        "fr": "Recommandations IA de 5 agents spécialisés. Recherchez, comparez et obtenez des conseils d'achat personnalisés.",
        "sv": "AI-drivna rekommendationer från 5 specialistagenter. Sök annonser, jämför modeller och få köpråd.",
        "lv": "AI ieteikumi no 5 specializētiem aģentiem. Meklējiet sludinājumus, salīziniet modeļus un saņemiet pirkšanas padomus.",
        "no": "AI-drevne anbefalinger fra 5 spesialistagenter. Søk annonser, sammenlign modeller og få kjøpsråd.",
        "da": "AI-drevne anbefalinger fra 5 specialistagenter. Søg annoncer, sammenlign modeller og få købsråd.",
        "pl": "Rekomendacje AI od 5 wyspecjalizowanych agentów. Szukaj ogłoszeń, porównuj modele i otrzymuj porady zakupowe.",
        "nl": "AI-gestuurde aanbevelingen van 5 gespecialiseerde agenten. Zoek advertenties, vergelijk modellen en ontvang koopadvies.",
        "fi": "Tekoälypohjaiset suositukset 5 erikoistuneelta agentilta. Etsi ilmoituksia, vertaile malleja ja saa ostoneuvoja.",
        "lt": "Dirbtinio intelekto rekomendacijos iš 5 specializuotų agentų. Ieškokite skelbimų, lyginkite modelius ir gaukite pirkimo patarimus.",
    },
    "feat_advisory_link": {
        "en": "Start a conversation", "et": "Alusta vestlust",
        "de": "Gespräch starten", "fr": "Démarrer une conversation",
        "sv": "Starta en konversation", "lv": "Sākt sarunu",
        "no": "Start en samtale", "da": "Start en samtale",
        "pl": "Rozpocznij rozmowę", "nl": "Start een gesprek",
        "fi": "Aloita keskustelu", "lt": "Pradėti pokalbį",
    },
    "feat_market": {
        "en": "Market Intelligence", "et": "Turuluure", "de": "Marktintelligenz",
        "fr": "Intelligence de marché", "sv": "Marknadsintelligens",
        "lv": "Tirgus izlūkošana", "no": "Markedsintelligens",
        "da": "Markedsintelligens", "pl": "Analiza rynku",
        "nl": "Marktintelligentie", "fi": "Markkinatieto", "lt": "Rinkos žvalgyba",
    },
    "feat_market_body": {
        "en": "Price trend visualizations, depreciation curves, and geographic comparisons. Track BMW, Mercedes, Audi and more across UK, Germany, and Europe.",
        "et": "Hinnatrendide visualiseeringud, väärtuse languse kõverad ja geograafilised võrdlused. Jälgi BMW, Mercedes, Audi ja teisi ÜK-s, Saksamaal ja Euroopas.",
        "de": "Preistrendvisualisierungen, Wertverlustkurven und geografische Vergleiche. Verfolgen Sie BMW, Mercedes, Audi und mehr in UK, Deutschland und Europa.",
        "fr": "Visualisations des tendances de prix, courbes de dépréciation et comparaisons géographiques.",
        "sv": "Pristrendvisualiseringar, deprecieringskurvor och geografiska jämförelser.",
        "lv": "Cenu tendenču vizualizācijas, nolietojuma līknes un ģeogrāfiskie salīdzinājumi.",
        "no": "Pristrendvisualiseringer, deprecieringskurver og geografiske sammenligninger.",
        "da": "Pristendvisualiseringer, deprecieringskurver og geografiske sammenligninger.",
        "pl": "Wizualizacje trendów cenowych, krzywe deprecjacji i porównania geograficzne.",
        "nl": "Prijstrendvisualisaties, afschrijvingscurves en geografische vergelijkingen.",
        "fi": "Hintatrendien visualisoinnit, arvonlaskukäyrät ja maantieteelliset vertailut.",
        "lt": "Kainų tendencijų vizualizacijos, nusidėvėjimo kreivės ir geografiniai palyginimai.",
    },
    "feat_market_link": {
        "en": "View market map", "et": "Vaata turukaart",
        "de": "Marktkarte ansehen", "fr": "Voir la carte du marché",
        "sv": "Se marknadskarta", "lv": "Skatīt tirgus karti",
        "no": "Se markedskart", "da": "Se markedskort",
        "pl": "Zobacz mapę rynku", "nl": "Marktkaart bekijken",
        "fi": "Näytä markkinakartta", "lt": "Žiūrėti rinkos žemėlapį",
    },
    "feat_valuation": {
        "en": "Valuation Tools", "et": "Hindamisvahendid", "de": "Bewertungstools",
        "fr": "Outils d'évaluation", "sv": "Värderingsverktyg",
        "lv": "Vērtēšanas rīki", "no": "Verdsettelsesverktøy",
        "da": "Værdiansættelsesværktøjer", "pl": "Narzędzia wyceny",
        "nl": "Waarderingstools", "fi": "Arvostustyökalut", "lt": "Vertinimo įrankiai",
    },
    "feat_valuation_body": {
        "en": "Get fair market value estimates based on comparable listings, mileage, year, and condition. Data-driven pricing powered by thousands of real listings.",
        "et": "Saa õiglase turuhinna hinnanguid võrreldavate kuulutuste, läbisõidu, aasta ja seisukorra põhjal.",
        "de": "Erhalten Sie Marktwertschätzungen basierend auf vergleichbaren Angeboten, Kilometerstand, Baujahr und Zustand.",
        "fr": "Obtenez des estimations de valeur marché basées sur des annonces comparables, le kilométrage, l'année et l'état.",
        "sv": "Få marknadsvärdesuppskattningar baserade på jämförbara annonser, mil, år och skick.",
        "lv": "Iegūstiet tirgus vērtības novērtējumus, pamatojoties uz salīdzināmiem sludinājumiem.",
        "no": "Få markedsverdivurderinger basert på sammenlignbare annonser.",
        "da": "Få markedsværdivurderinger baseret på sammenlignelige annoncer.",
        "pl": "Otrzymaj wyceny wartości rynkowej na podstawie porównywalnych ogłoszeń.",
        "nl": "Ontvang marktwaardeschattingen op basis van vergelijkbare advertenties.",
        "fi": "Saa markkina-arvoarvioita vertailukelpoisten ilmoitusten perusteella.",
        "lt": "Gaukite rinkos vertės įvertinimus pagal palyginamus skelbimus.",
    },
    "feat_valuation_link": {
        "en": "Get a valuation", "et": "Saa hindamine",
        "de": "Bewertung erhalten", "fr": "Obtenir une évaluation",
        "sv": "Få en värdering", "lv": "Iegūt vērtējumu",
        "no": "Få en verdivurdering", "da": "Få en vurdering",
        "pl": "Uzyskaj wycenę", "nl": "Waardering aanvragen",
        "fi": "Pyydä arvio", "lt": "Gauti vertinimą",
    },

    # -- How It Works --
    "how_title": {
        "en": "How It Works", "et": "Kuidas see töötab",
        "de": "So funktioniert es", "fr": "Comment ça marche",
        "sv": "Så fungerar det", "lv": "Kā tas darbojas",
        "no": "Slik fungerer det", "da": "Sådan fungerer det",
        "pl": "Jak to działa", "nl": "Hoe het werkt",
        "fi": "Näin se toimii", "lt": "Kaip tai veikia",
    },
    "how_01_title": {
        "en": "Search", "et": "Otsi", "de": "Suchen",
        "fr": "Recherchez", "sv": "Sök", "lv": "Meklējiet",
        "no": "Søk", "da": "Søg", "pl": "Szukaj",
        "nl": "Zoek", "fi": "Etsi", "lt": "Ieškokite",
    },
    "how_01_body": {
        "en": "Tell us what you're looking for — brand, model, budget, or just describe your ideal car. Our AI routes your query to the right specialist.",
        "et": "Rääkige meile, mida otsite — bränd, mudel, eelarve või kirjeldage oma ideaalset autot.",
        "de": "Sagen Sie uns, was Sie suchen — Marke, Modell, Budget, oder beschreiben Sie einfach Ihr Wunschauto.",
        "fr": "Dites-nous ce que vous cherchez — marque, modèle, budget, ou décrivez votre voiture idéale.",
        "sv": "Berätta vad du letar efter — märke, modell, budget, eller beskriv din drömbil.",
        "lv": "Pastāstiet, ko meklējat — zīmolu, modeli, budžetu vai aprakstiet savu ideālo auto.",
        "no": "Fortell oss hva du leter etter — merke, modell, budsjett, eller beskriv din drømmebil.",
        "da": "Fortæl os hvad du leder efter — mærke, model, budget, eller beskriv din drømmebil.",
        "pl": "Powiedz nam, czego szukasz — marka, model, budżet lub opisz swój wymarzony samochód.",
        "nl": "Vertel ons wat u zoekt — merk, model, budget, of beschrijf uw ideale auto.",
        "fi": "Kerro mitä etsit — merkki, malli, budjetti tai kuvaile unelma-autoasi.",
        "lt": "Pasakykite, ko ieškote — prekės ženklą, modelį, biudžetą arba aprašykite savo svajonių automobilį.",
    },
    "how_02_title": {
        "en": "Analyze", "et": "Analüüsi", "de": "Analysieren",
        "fr": "Analysez", "sv": "Analysera", "lv": "Analizējiet",
        "no": "Analyser", "da": "Analyser", "pl": "Analizuj",
        "nl": "Analyseer", "fi": "Analysoi", "lt": "Analizuokite",
    },
    "how_02_body": {
        "en": "The agent searches across AutoTrader, mobile.de, AutoScout24, and Autohero. It compares prices, checks depreciation, and generates visualizations.",
        "et": "Agent otsib AutoTraderist, mobile.de-st, AutoScout24-st ja Autoherost. Võrdleb hindu, kontrollib väärtuse langust ja loob visualiseeringuid.",
        "de": "Der Agent durchsucht AutoTrader, mobile.de, AutoScout24 und Autohero. Er vergleicht Preise, prüft den Wertverlust und erstellt Visualisierungen.",
        "fr": "L'agent recherche sur AutoTrader, mobile.de, AutoScout24 et Autohero. Il compare les prix et génère des visualisations.",
        "sv": "Agenten söker på AutoTrader, mobile.de, AutoScout24 och Autohero. Den jämför priser och skapar visualiseringar.",
        "lv": "Aģents meklē AutoTrader, mobile.de, AutoScout24 un Autohero. Salīzina cenas un veido vizualizācijas.",
        "no": "Agenten søker på AutoTrader, mobile.de, AutoScout24 og Autohero.",
        "da": "Agenten søger på AutoTrader, mobile.de, AutoScout24 og Autohero.",
        "pl": "Agent przeszukuje AutoTrader, mobile.de, AutoScout24 i Autohero. Porównuje ceny i tworzy wizualizacje.",
        "nl": "De agent doorzoekt AutoTrader, mobile.de, AutoScout24 en Autohero.",
        "fi": "Agentti etsii AutoTraderista, mobile.de:stä, AutoScout24:stä ja Autoherosta.",
        "lt": "Agentas ieško AutoTrader, mobile.de, AutoScout24 ir Autohero.",
    },
    "how_03_title": {
        "en": "Decide", "et": "Otsusta", "de": "Entscheiden",
        "fr": "Décidez", "sv": "Besluta", "lv": "Izlemiet",
        "no": "Beslutt", "da": "Beslut", "pl": "Zdecyduj",
        "nl": "Beslis", "fi": "Päätä", "lt": "Nuspreskite",
    },
    "how_03_body": {
        "en": "Get a fair price estimate, compare alternatives, and find the best deal. Whether you're buying your first BMW or upgrading to a Porsche.",
        "et": "Õiglase hinna hinnang, alternatiivide võrdlus ja parima pakkumise leidmine. Olenemata sellest, kas ostad esimest BMW-d või uuendad Porschele.",
        "de": "Erhalten Sie eine faire Preisschätzung, vergleichen Sie Alternativen und finden Sie das beste Angebot.",
        "fr": "Obtenez une estimation de prix équitable, comparez les alternatives et trouvez la meilleure offre.",
        "sv": "Få en rättvis prisuppskattning, jämför alternativ och hitta det bästa erbjudandet.",
        "lv": "Iegūstiet godīgu cenas novērtējumu, salīziniet alternatīvas un atrodiet labāko piedāvājumu.",
        "no": "Få et rettferdig prisestimat, sammenlign alternativer og finn det beste tilbudet.",
        "da": "Få et retfærdigt prisestimat, sammenlign alternativer og find det bedste tilbud.",
        "pl": "Uzyskaj uczciwą wycenę, porównaj alternatywy i znajdź najlepszą ofertę.",
        "nl": "Ontvang een eerlijke prijsschatting, vergelijk alternatieven en vind de beste deal.",
        "fi": "Saa reilu hinta-arvio, vertaile vaihtoehtoja ja löydä paras tarjous.",
        "lt": "Gaukite sąžiningą kainos įvertinimą, palyginkite alternatyvas ir raskite geriausį pasiūlymą.",
    },

    # -- Agents --
    "agents_title": {
        "en": "5 Specialist Agents", "et": "5 erialagenti",
        "de": "5 Spezialagenten", "fr": "5 agents spécialisés",
        "sv": "5 specialistagenter", "lv": "5 specializēti aģenti",
        "no": "5 spesialistagenter", "da": "5 specialistagenter",
        "pl": "5 wyspecjalizowanych agentów", "nl": "5 gespecialiseerde agenten",
        "fi": "5 erikoistunutta agenttia", "lt": "5 specializuoti agentai",
    },
    "agents_subtitle": {
        "en": "Each trained for a specific aspect of car advisory.",
        "et": "Igaüks koolitatud konkreetse autonõustamise valdkonna jaoks.",
        "de": "Jeder für einen spezifischen Aspekt der Autoberatung ausgebildet.",
        "fr": "Chacun formé pour un aspect spécifique du conseil automobile.",
        "sv": "Var och en utbildad för en specifik aspekt av bilrådgivning.",
        "lv": "Katrs apmācīts konkrētam auto konsultāciju aspektam.",
        "no": "Hver trent for en spesifikk del av bilrådgivning.",
        "da": "Hver trænet til et specifikt aspekt af bilrådgivning.",
        "pl": "Każdy wyszkolony w konkretnym aspekcie doradztwa samochodowego.",
        "nl": "Elk getraind voor een specifiek aspect van autoadvies.",
        "fi": "Jokainen koulutettu tiettyyn autoneuvonnan osa-alueeseen.",
        "lt": "Kiekvienas apmokytas konkrečiam automobilių konsultavimo aspektui.",
    },

    # -- CTA --
    "cta_headline": {
        "en": "Find your next car, smarter.",
        "et": "Leia oma järgmine auto nutikamalt.",
        "de": "Finden Sie Ihr nächstes Auto — intelligenter.",
        "fr": "Trouvez votre prochaine voiture plus intelligemment.",
        "sv": "Hitta din nästa bil smartare.",
        "lv": "Atrodiet savu nākamo auto gudrāk.",
        "no": "Finn din neste bil smartere.",
        "da": "Find din næste bil smartere.",
        "pl": "Znajdź swój następny samochód mądrzej.",
        "nl": "Vind uw volgende auto — slimmer.",
        "fi": "Löydä seuraava autosi älykkäämmin.",
        "lt": "Raskite savo kitą automobilį protingiau.",
    },
    "cta_body": {
        "en": "AI-powered car advisory across 4 European marketplaces. Search, compare, and buy with confidence.",
        "et": "Tehisintellektil põhinev autonõustamine 4 Euroopa turul. Otsi, võrdle ja osta kindlalt.",
        "de": "KI-gestützte Autoberatung über 4 europäische Marktplätze. Suchen, vergleichen und sicher kaufen.",
        "fr": "Conseil automobile IA sur 4 places de marché européennes.",
        "sv": "AI-driven bilrådgivning över 4 europeiska marknadsplatser.",
        "lv": "AI auto konsultācijas 4 Eiropas tirdzniecības platformās.",
        "no": "AI-drevet bilrådgivning over 4 europeiske markedsplasser.",
        "da": "AI-drevet bilrådgivning på 4 europæiske markedspladser.",
        "pl": "Doradztwo samochodowe AI na 4 europejskich platformach.",
        "nl": "AI-gestuurd autoadvies op 4 Europese marktplaatsen.",
        "fi": "Tekoälypohjainen autoneuvonta 4 eurooppalaisella markkinapaikalla.",
        "lt": "AI automobilių konsultavimas 4 Europos prekių aikštelėse.",
    },

    # -- Footer --
    "footer_desc": {
        "en": "AI-powered car advisory and comparison platform. We help buyers find, compare, and value premium cars across European marketplaces.",
        "et": "Tehisintellektil põhinev autonõustamise ja võrdlusplatvorm.",
        "de": "KI-gestützte Autoberatungs- und Vergleichsplattform.",
        "fr": "Plateforme de conseil et comparaison automobile par IA.",
        "sv": "AI-driven plattform för bilrådgivning och jämförelse.",
        "lv": "AI auto konsultāciju un salīdzināšanas platforma.",
        "no": "AI-drevet plattform for bilrådgivning og sammenligning.",
        "da": "AI-drevet platform for bilrådgivning og sammenligning.",
        "pl": "Platforma doradztwa i porównywania samochodów wspierana AI.",
        "nl": "AI-gestuurd platform voor autoadvies en vergelijking.",
        "fi": "Tekoälypohjainen autoneuvonta- ja vertailualusta.",
        "lt": "Dirbtinio intelekto valdoma automobilių konsultavimo ir palyginimo platforma.",
    },
    "footer_platform": {
        "en": "Platform", "et": "Platvorm", "de": "Plattform",
        "fr": "Plateforme", "sv": "Plattform", "lv": "Platforma",
        "no": "Plattform", "da": "Platform", "pl": "Platforma",
        "nl": "Platform", "fi": "Alusta", "lt": "Platforma",
    },
    "footer_resources": {
        "en": "Resources", "et": "Ressursid", "de": "Ressourcen",
        "fr": "Ressources", "sv": "Resurser", "lv": "Resursi",
        "no": "Ressurser", "da": "Ressourcer", "pl": "Zasoby",
        "nl": "Bronnen", "fi": "Resurssit", "lt": "Ištekliai",
    },
    "footer_legal": {
        "en": "Legal", "et": "Juriidiline", "de": "Rechtliches",
        "fr": "Légal", "sv": "Juridiskt", "lv": "Juridiskā",
        "no": "Juridisk", "da": "Juridisk", "pl": "Prawne",
        "nl": "Juridisch", "fi": "Oikeudellinen", "lt": "Teisinė informacija",
    },
    "footer_terms": {
        "en": "Terms of Service", "et": "Teenuse tingimused",
        "de": "Nutzungsbedingungen", "fr": "Conditions d'utilisation",
        "sv": "Användarvillkor", "lv": "Lietošanas noteikumi",
        "no": "Bruksvilår", "da": "Brugsvilår", "pl": "Regulamin",
        "nl": "Servicevoorwaarden", "fi": "Käyttöehdot", "lt": "Paslaugų sąlygos",
    },
    "footer_privacy": {
        "en": "Privacy Policy", "et": "Privaatsuspoliitika",
        "de": "Datenschutzrichtlinie", "fr": "Politique de confidentialité",
        "sv": "Integritetspolicy", "lv": "Privātuma politika",
        "no": "Personvernregler", "da": "Privatlivspolitik",
        "pl": "Polityka prywatności", "nl": "Privacybeleid",
        "fi": "Tietosuojakäytäntö", "lt": "Privatumo politika",
    },
    "footer_copyright": {
        "en": "© 2026 CarHero. All rights reserved.",
        "et": "© 2026 CarHero. Kõik õigused kaitstud.",
        "de": "© 2026 CarHero. Alle Rechte vorbehalten.",
        "fr": "© 2026 CarHero. Tous droits réservés.",
        "sv": "© 2026 CarHero. Alla rättigheter förbehållna.",
        "lv": "© 2026 CarHero. Visas tiesības aizsargātas.",
        "no": "© 2026 CarHero. Alle rettigheter forbeholdt.",
        "da": "© 2026 CarHero. Alle rettigheder forbeholdes.",
        "pl": "© 2026 CarHero. Wszelkie prawa zastrzeżone.",
        "nl": "© 2026 CarHero. Alle rechten voorbehouden.",
        "fi": "© 2026 CarHero. Kaikki oikeudet pidätetään.",
        "lt": "© 2026 CarHero. Visos teisės saugomos.",
    },
    "footer_disclaimer": {
        "en": "Car valuations are estimates based on market data. Actual prices may vary.",
        "et": "Autode hindamised on hinnangud turuandmete põhjal. Tegelikud hinnad võivad erineda.",
        "de": "Fahrzeugbewertungen sind Schätzungen auf Basis von Marktdaten. Tatsächliche Preise können abweichen.",
        "fr": "Les évaluations automobiles sont des estimations basées sur les données du marché. Les prix réels peuvent varier.",
        "sv": "Bilvärderingar är uppskattningar baserade på marknadsdata. Faktiska priser kan variera.",
        "lv": "Auto vērtējumi ir aplēses, kas balstītas uz tirgus datiem.",
        "no": "Bilvurderinger er estimater basert på markedsdata.",
        "da": "Bilvurderinger er estimater baseret på markedsdata.",
        "pl": "Wyceny samochodów to szacunki oparte na danych rynkowych.",
        "nl": "Autowaarderingen zijn schattingen op basis van marktgegevens.",
        "fi": "Autojen arviot perustuvat markkinadataan. Todelliset hinnat voivat vaihdella.",
        "lt": "Automobilių vertinimai yra įvertinimai, paremti rinkos duomenimis.",
    },

    # -- Chat UI --
    "chat_new": {
        "en": "+ New chat", "et": "+ Uus vestlus", "de": "+ Neuer Chat",
        "fr": "+ Nouveau chat", "sv": "+ Ny chatt", "lv": "+ Jauna saruna",
        "no": "+ Ny chat", "da": "+ Ny chat", "pl": "+ Nowy czat",
        "nl": "+ Nieuw gesprek", "fi": "+ Uusi keskustelu", "lt": "+ Naujas pokalbis",
    },
    "chat_history": {
        "en": "History", "et": "Ajalugu", "de": "Verlauf",
        "fr": "Historique", "sv": "Historik", "lv": "Vēsture",
        "no": "Historikk", "da": "Historik", "pl": "Historia",
        "nl": "Geschiedenis", "fi": "Historia", "lt": "Istorija",
    },
    "chat_agents": {
        "en": "Agents", "et": "Agendid", "de": "Agenten",
        "fr": "Agents", "sv": "Agenter", "lv": "Aģenti",
        "no": "Agenter", "da": "Agenter", "pl": "Agenci",
        "nl": "Agenten", "fi": "Agentit", "lt": "Agentai",
    },
    "chat_welcome_title": {
        "en": "CarHero AI Advisor",
        "et": "CarHero tehisintellekt-nõustaja",
        "de": "CarHero KI-Berater",
        "fr": "CarHero Conseiller IA",
        "sv": "CarHero AI-rådgivare",
        "lv": "CarHero AI konsultants",
        "no": "CarHero AI-rådgiver",
        "da": "CarHero AI-rådgiver",
        "pl": "CarHero doradca AI",
        "nl": "CarHero AI-adviseur",
        "fi": "CarHero AI-neuvoja",
        "lt": "CarHero AI patarėjas",
    },
    "chat_welcome_body": {
        "en": "Ask about car models, market trends, valuations, or get buying advice.",
        "et": "Küsi automudelite, turutrendide, hindamiste või ostunõu kohta.",
        "de": "Fragen Sie nach Automodellen, Markttrends, Bewertungen oder Kaufberatung.",
        "fr": "Posez des questions sur les modèles, les tendances, les évaluations ou obtenez des conseils d'achat.",
        "sv": "Fråga om bilmodeller, marknadstrender, värderingar eller få köpråd.",
        "lv": "Jautājiet par auto modeļiem, tirgus tendencēm, vērtējumiem vai pirkšanas padomiem.",
        "no": "Spør om bilmodeller, markedstrender, verdivurderinger eller kjøpsråd.",
        "da": "Spørg om bilmodeller, markedstendenser, vurderinger eller købsråd.",
        "pl": "Zapytaj o modele samochodów, trendy rynkowe, wyceny lub porady zakupowe.",
        "nl": "Vraag over automodellen, markttrends, waarderingen of koopadvies.",
        "fi": "Kysy automalleista, markkinatrendeistä, arvioista tai ostoneuvoja.",
        "lt": "Klauskite apie automobilių modelius, rinkos tendencijas, vertinimus ar pirkimo patarimus.",
    },
    "chat_placeholder": {
        "en": "Search for a car, compare models, or get a valuation...",
        "et": "Otsi autot, võrdle mudeleid või saa hindamine...",
        "de": "Suchen Sie ein Auto, vergleichen Sie Modelle oder lassen Sie sich beraten...",
        "fr": "Recherchez une voiture, comparez des modèles ou obtenez une évaluation...",
        "sv": "Sök en bil, jämför modeller eller få en värdering...",
        "lv": "Meklējiet auto, salīziniet modeļus vai iegūstiet vērtējumu...",
        "no": "Søk etter en bil, sammenlign modeller eller få en verdivurdering...",
        "da": "Søg efter en bil, sammenlign modeller eller få en vurdering...",
        "pl": "Szukaj samochodu, porównuj modele lub uzyskaj wycenę...",
        "nl": "Zoek een auto, vergelijk modellen of vraag een waardering aan...",
        "fi": "Etsi autoa, vertaile malleja tai pyydä arvio...",
        "lt": "Ieškokite automobilio, lyginkite modelius arba gaukite vertinimą...",
    },

    "chat_no_sessions": {
        "en": "No conversations yet", "et": "Vestlusi pole veel", "de": "Noch keine Unterhaltungen",
        "fr": "Pas encore de conversations", "sv": "Inga konversationer ännu",
        "lv": "Vēl nav sarunu", "no": "Ingen samtaler ennå", "da": "Ingen samtaler endnu",
        "pl": "Brak rozmów", "nl": "Nog geen gesprekken",
        "fi": "Ei keskusteluja vielä", "lt": "Pokalbių dar nėra",
    },
    "chat_copy": {
        "en": "Copy", "et": "Kopeeri", "de": "Kopieren",
        "fr": "Copier", "sv": "Kopiera", "lv": "Kopēt",
        "no": "Kopier", "da": "Kopier", "pl": "Kopiuj",
        "nl": "Kopiëren", "fi": "Kopioi", "lt": "Kopijuoti",
    },
    "chat_share": {
        "en": "Share", "et": "Jaga", "de": "Teilen",
        "fr": "Partager", "sv": "Dela", "lv": "Dalīties",
        "no": "Del", "da": "Del", "pl": "Udostępnij",
        "nl": "Delen", "fi": "Jaa", "lt": "Dalintis",
    },
    "chat_canvas": {
        "en": "Canvas", "et": "Lõuend", "de": "Leinwand",
        "fr": "Canvas", "sv": "Canvas", "lv": "Audekls",
        "no": "Lerret", "da": "Lærred", "pl": "Kanwa",
        "nl": "Canvas", "fi": "Kanvas", "lt": "Drobė",
    },
    "chat_signin_title": {
        "en": "Sign In", "et": "Logi sisse", "de": "Anmelden",
        "fr": "Connexion", "sv": "Logga in", "lv": "Pieslēgties",
        "no": "Logg inn", "da": "Log ind", "pl": "Zaloguj się",
        "nl": "Inloggen", "fi": "Kirjaudu sisään", "lt": "Prisijungti",
    },
    "chat_signin_body": {
        "en": "Enter your email to save chat history.", "et": "Sisesta email vestlusajaloo salvestamiseks.",
        "de": "Geben Sie Ihre E-Mail ein, um den Chatverlauf zu speichern.",
        "fr": "Entrez votre email pour sauvegarder l'historique.",
        "sv": "Ange din e-post för att spara chatthistorik.",
        "lv": "Ievadiet e-pastu, lai saglabātu sarunu vēsturi.",
        "no": "Skriv inn e-posten din for å lagre chattehistorikk.",
        "da": "Indtast din e-mail for at gemme chathistorik.",
        "pl": "Wpisz email, aby zapisać historię czatu.",
        "nl": "Voer uw e-mail in om chatgeschiedenis op te slaan.",
        "fi": "Syötä sähköpostisi tallentaaksesi keskusteluhistorian.",
        "lt": "Įveskite el. paštą, kad išsaugotumėte pokalbių istoriją.",
    },
    "chat_sign_in": {
        "en": "Sign In", "et": "Logi sisse", "de": "Anmelden",
        "fr": "Connexion", "sv": "Logga in", "lv": "Pieslēgties",
        "no": "Logg inn", "da": "Log ind", "pl": "Zaloguj się",
        "nl": "Inloggen", "fi": "Kirjaudu", "lt": "Prisijungti",
    },
    "chat_sign_out": {
        "en": "Sign Out", "et": "Logi välja", "de": "Abmelden",
        "fr": "Déconnexion", "sv": "Logga ut", "lv": "Iziet",
        "no": "Logg ut", "da": "Log ud", "pl": "Wyloguj",
        "nl": "Uitloggen", "fi": "Kirjaudu ulos", "lt": "Atsijungti",
    },
    "chat_cancel": {
        "en": "Cancel", "et": "Tühista", "de": "Abbrechen",
        "fr": "Annuler", "sv": "Avbryt", "lv": "Atcelt",
        "no": "Avbryt", "da": "Annuller", "pl": "Anuluj",
        "nl": "Annuleren", "fi": "Peruuta", "lt": "Atšaukti",
    },
    "chat_artifacts_title": {
        "en": "Results", "et": "Tulemused", "de": "Ergebnisse",
        "fr": "Résultats", "sv": "Resultat", "lv": "Rezultāti",
        "no": "Resultater", "da": "Resultater", "pl": "Wyniki",
        "nl": "Resultaten", "fi": "Tulokset", "lt": "Rezultatai",
    },
    "chat_artifacts_subtitle": {
        "en": "Charts, tables, and search results", "et": "Graafikud, tabelid ja otsingutulemused",
        "de": "Diagramme, Tabellen und Suchergebnisse",
        "fr": "Graphiques, tableaux et résultats de recherche",
        "sv": "Diagram, tabeller och sökresultat",
        "lv": "Diagrammas, tabulas un meklēšanas rezultāti",
        "no": "Diagrammer, tabeller og søkeresultater",
        "da": "Diagrammer, tabeller og søgeresultater",
        "pl": "Wykresy, tabele i wyniki wyszukiwania",
        "nl": "Grafieken, tabellen en zoekresultaten",
        "fi": "Kaaviot, taulukot ja hakutulokset",
        "lt": "Diagramos, lentelės ir paieškos rezultatai",
    },

    # -- JS strings --
    "js_thinking": {
        "en": "Thinking", "et": "Mõtleb", "de": "Denkt nach",
        "fr": "Réflexion", "sv": "Tänker", "lv": "Domā",
        "no": "Tenker", "da": "Tænker", "pl": "Myśli",
        "nl": "Denkt na", "fi": "Miettii", "lt": "Mąsto",
    },
    "js_calling": {
        "en": "Calling", "et": "Kutsub", "de": "Ruft auf",
        "fr": "Appel", "sv": "Anropar", "lv": "Izsauc",
        "no": "Kaller", "da": "Kalder", "pl": "Wywołuje",
        "nl": "Roept aan", "fi": "Kutsuu", "lt": "Kviečia",
    },
    "js_copy_csv": {
        "en": "Copy CSV", "et": "Kopeeri CSV", "de": "CSV kopieren",
        "fr": "Copier CSV", "sv": "Kopiera CSV", "lv": "Kopēt CSV",
        "no": "Kopier CSV", "da": "Kopier CSV", "pl": "Kopiuj CSV",
        "nl": "CSV kopiëren", "fi": "Kopioi CSV", "lt": "Kopijuoti CSV",
    },
    "js_copied": {
        "en": "Copied!", "et": "Kopeeritud!", "de": "Kopiert!",
        "fr": "Copié !", "sv": "Kopierat!", "lv": "Nokopēts!",
        "no": "Kopiert!", "da": "Kopieret!", "pl": "Skopiowano!",
        "nl": "Gekopieerd!", "fi": "Kopioitu!", "lt": "Nukopijuota!",
    },
}

# -- Agent translations --
AGENT_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "car_search": {
        "name": {"en": "Car Search", "et": "Auto otsing", "de": "Autosuche", "fr": "Recherche auto", "sv": "Bilsökning", "nl": "Auto zoeken", "fi": "Autohaku", "lt": "Automobilio paieška"},
        "one_liner": {"en": "Find cars matching your criteria across 4 marketplaces.", "et": "Leia autod, mis vastavad sinu kriteeriumidele 4 turult.", "de": "Finden Sie Autos nach Ihren Kriterien auf 4 Marktplätzen.", "fr": "Trouvez des voitures correspondant à vos critères.", "sv": "Hitta bilar som matchar dina kriterier.", "nl": "Vind auto's die aan uw criteria voldoen.", "fi": "Löydä autoja kriteeriesi mukaan.", "lt": "Raskite automobilius pagal savo kriterijus."},
    },
    "market_analyst": {
        "name": {"en": "Market Analyst", "et": "Turuanalüütik", "de": "Marktanalyst", "fr": "Analyste de marché", "sv": "Marknadsanalytiker", "nl": "Marktanalist", "fi": "Markkina-analyytikko", "lt": "Rinkos analitikas"},
        "one_liner": {"en": "Price trends, depreciation curves, and geographic comparisons.", "et": "Hinnatrendid, väärtuse languse kõverad ja geograafilised võrdlused.", "de": "Preistrends, Wertverlustkurven und geografische Vergleiche.", "fr": "Tendances de prix, courbes de dépréciation et comparaisons géographiques.", "sv": "Pristrender, deprecieringskurvor och geografiska jämförelser.", "nl": "Prijstrends, afschrijvingscurves en geografische vergelijkingen.", "fi": "Hintatrendit, arvonlaskukäyrät ja maantieteelliset vertailut.", "lt": "Kainų tendencijos, nusidėvėjimo kreivės ir geografiniai palyginimai."},
    },
    "valuator": {
        "name": {"en": "Valuator", "et": "Hindaja", "de": "Bewerter", "fr": "Évaluateur", "sv": "Värderare", "nl": "Taxateur", "fi": "Arvioija", "lt": "Vertintojas"},
        "one_liner": {"en": "Fair value estimation from comparable listings and market data.", "et": "Õiglase väärtuse hindamine võrreldavate kuulutuste ja turuandmete põhjal.", "de": "Marktwertschätzung aus vergleichbaren Angeboten und Marktdaten.", "fr": "Estimation de la juste valeur à partir d'annonces comparables.", "sv": "Marknadsvärdering från jämförbara annonser.", "nl": "Waardeschatting op basis van vergelijkbare advertenties.", "fi": "Käyvän arvon arviointi vertailukelpoisten ilmoitusten perusteella.", "lt": "Tikrosios vertės įvertinimas pagal palyginamus skelbimus."},
    },
    "car_compare": {
        "name": {"en": "Car Compare", "et": "Auto võrdlus", "de": "Autovergleich", "fr": "Comparaison auto", "sv": "Biljämförelse", "nl": "Auto vergelijken", "fi": "Autovertailu", "lt": "Automobilių palyginimas"},
        "one_liner": {"en": "Side-by-side comparison of models, specs, and pricing.", "et": "Mudelite, spetsifikatsioonide ja hindade kõrvutivõrdlus.", "de": "Vergleich von Modellen, Spezifikationen und Preisen nebeneinander.", "fr": "Comparaison côte à côte des modèles, spécifications et prix.", "sv": "Jämförelse av modeller, specifikationer och priser sida vid sida.", "nl": "Vergelijking van modellen, specificaties en prijzen naast elkaar.", "fi": "Mallien, teknisten tietojen ja hintojen vertailu rinnakkain.", "lt": "Modelių, specifikacijų ir kainų palyginimas greta."},
    },
    "advisor": {
        "name": {"en": "Buying Advisor", "et": "Ostunõustaja", "de": "Kaufberater", "fr": "Conseiller d'achat", "sv": "Köprådgivare", "nl": "Koopadviseur", "fi": "Ostoneuvoja", "lt": "Pirkimo patarėjas"},
        "one_liner": {"en": "Personalized recommendations based on your needs and budget.", "et": "Personaalsed soovitused sinu vajaduste ja eelarve põhjal.", "de": "Personalisierte Empfehlungen basierend auf Ihren Bedürfnissen und Budget.", "fr": "Recommandations personnalisées selon vos besoins et budget.", "sv": "Personliga rekommendationer baserade på dina behov och budget.", "nl": "Gepersonaliseerde aanbevelingen op basis van uw behoeften en budget.", "fi": "Henkilökohtaiset suositukset tarpeidesi ja budjettisi perusteella.", "lt": "Asmeninės rekomendacijos pagal jūsų poreikius ir biudžetą."},
    },
}

# -- Category translations --
CATEGORY_TRANSLATIONS: dict[str, dict[str, dict[str, str]]] = {
    "search": {
        "name": {"en": "Car Search & Discovery", "et": "Auto otsing ja avastamine", "de": "Autosuche & Entdeckung", "fr": "Recherche & Découverte", "sv": "Bilsökning & Upptäckt", "nl": "Auto zoeken & Ontdekking", "fi": "Autohaku ja löytäminen", "lt": "Automobilių paieška ir atradimai"},
    },
    "market": {
        "name": {"en": "Market Intelligence", "et": "Turuluure", "de": "Marktintelligenz", "fr": "Intelligence de marché", "sv": "Marknadsintelligens", "nl": "Marktintelligentie", "fi": "Markkinatieto", "lt": "Rinkos žvalgyba"},
    },
    "advisory": {
        "name": {"en": "Car Advisory", "et": "Autonõustamine", "de": "Autoberatung", "fr": "Conseil automobile", "sv": "Bilrådgivning", "nl": "Autoadvies", "fi": "Autoneuvonta", "lt": "Automobilių konsultacijos"},
    },
}
