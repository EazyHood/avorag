"""Conocimiento de dominio agronómico, sin dependencias de infraestructura."""

from __future__ import annotations

import re
import unicodedata


def _noacc(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")

# Ingredientes activos reconocidos para la detección de los guardarraíles (NO es una lista de
# productos registrados ni autoriza su uso; el registro/vigencia los define el ICA en SimplifICA).
# Ampliada a moléculas modernas (diamidas, sulfoximinas, SDHI, cetoenoles, butenólidos, acaricidas
# específicos, estrobilurinas…) porque una lista corta dejaba "bajar la guardia" justo donde más se
# aplica hoy. Se incluyen variantes ES/EN de grafía para que la coincidencia por subcadena no falle.
ACTIVE_INGREDIENTS: tuple[str, ...] = (
    # — Insecticidas/acaricidas: clásicos —
    "abamectina",
    "spinetoram",
    "spinosad",
    "imidacloprid",
    "thiamethoxam",
    "tiametoxam",
    "acetamiprid",
    "spirotetramat",
    "espirotetramat",
    "clorantraniliprol",
    "clorpirifos",
    "lambda-cialotrina",
    "lambdacialotrina",
    "cipermetrina",
    "deltametrina",
    "buprofezin",
    "pyriproxyfen",
    "piriproxifen",
    "azadiractina",
    "bacillus thuringiensis",
    "beauveria bassiana",
    "metarhizium",
    "trichoderma",
    "azufre",
    "aceite agricola",
    # — Insecticidas/acaricidas: modernos (lo que faltaba) —
    "ciantraniliprol",
    "cyantraniliprole",
    "flubendiamida",
    "emamectina",
    "sulfoxaflor",
    "flonicamida",
    "flupiradifurona",
    "flupyradifurone",
    "ciflumetofeno",
    "ciflumetofen",
    "espirodiclofeno",
    "spirodiclofen",
    "espiromesifeno",
    "spiromesifen",
    "clorfenapir",
    "chlorfenapyr",
    "tolfenpirad",
    "etoxazol",
    "fenpiroximato",
    "piridaben",
    "bifenazato",
    "fenazaquin",
    "milbemectina",
    "fipronil",
    "metomilo",
    "metoxifenozida",
    "novaluron",
    "lufenuron",
    "indoxacarb",
    "indoxacarbo",
    # — Fungicidas: clásicos —
    "fosetil-aluminio",
    "fosetil",
    "metalaxil",
    "mancozeb",
    "oxicloruro de cobre",
    "hidroxido de cobre",
    "propiconazol",
    "difenoconazol",
    "azoxistrobina",
    "fosfito",
    # — Fungicidas: modernos (SDHI, QoI, CAA, etc.) —
    "fluopyram",
    "fluopiram",
    "fluxapiroxad",
    "boscalid",
    "piraclostrobina",
    "trifloxistrobina",
    "kresoxim",
    "ciazofamida",
    "ametoctradina",
    "mandipropamida",
    "dimetomorf",
    "fluazinam",
    "tebuconazol",
    "ciproconazol",
    "fenbuconazol",
    "fenhexamida",
    "ciprodinil",
    "fludioxonil",
    "captan",
    "clorotalonil",
    "metiram",
    "folpet",
    # — Herbicidas de uso en calle/cobertura —
    "glifosato",
    "glufosinato",
)


# Grupos de modo de acción (IRAC = insecticidas/acaricidas, FRAC = fungicidas) para apoyar la
# estrategia anti-resistencia. NO exhaustivo; mapea los i.a. más usados en aguacate. Sirve para
# recordar la ROTACIÓN de grupos (no repetir el mismo grupo en aplicaciones consecutivas), no para
# recetar. Fuente: clasificaciones IRAC/FRAC públicas (verificar la versión vigente).
MODE_OF_ACTION_GROUP: dict[str, str] = {
    # Insecticidas/acaricidas (IRAC)
    "abamectina": "IRAC 6",
    "emamectina": "IRAC 6",
    "milbemectina": "IRAC 6",
    "spinosad": "IRAC 5",
    "spinetoram": "IRAC 5",
    "imidacloprid": "IRAC 4A",
    "thiamethoxam": "IRAC 4A",
    "tiametoxam": "IRAC 4A",
    "acetamiprid": "IRAC 4A",
    "sulfoxaflor": "IRAC 4C",
    "flupiradifurona": "IRAC 4D",
    "flupyradifurone": "IRAC 4D",
    "clorpirifos": "IRAC 1B",
    "metomilo": "IRAC 1A",
    "fipronil": "IRAC 2B",
    "lambda-cialotrina": "IRAC 3A",
    "lambdacialotrina": "IRAC 3A",
    "cipermetrina": "IRAC 3A",
    "deltametrina": "IRAC 3A",
    "clorantraniliprol": "IRAC 28",
    "ciantraniliprol": "IRAC 28",
    "cyantraniliprole": "IRAC 28",
    "flubendiamida": "IRAC 28",
    "spirotetramat": "IRAC 23",
    "espirotetramat": "IRAC 23",
    "espirodiclofeno": "IRAC 23",
    "spirodiclofen": "IRAC 23",
    "espiromesifeno": "IRAC 23",
    "spiromesifen": "IRAC 23",
    "buprofezin": "IRAC 16",
    "pyriproxyfen": "IRAC 7C",
    "piriproxifen": "IRAC 7C",
    "metoxifenozida": "IRAC 18",
    "novaluron": "IRAC 15",
    "lufenuron": "IRAC 15",
    "clorfenapir": "IRAC 13",
    "chlorfenapyr": "IRAC 13",
    "indoxacarb": "IRAC 22A",
    "indoxacarbo": "IRAC 22A",
    "flonicamida": "IRAC 29",
    "ciflumetofeno": "IRAC 25",
    "ciflumetofen": "IRAC 25",
    "etoxazol": "IRAC 10B",
    "bifenazato": "IRAC 20D",
    "tolfenpirad": "IRAC 21A",
    "fenpiroximato": "IRAC 21A",
    "piridaben": "IRAC 21A",
    "fenazaquin": "IRAC 21A",
    "azadiractina": "IRAC UN",
    "bacillus thuringiensis": "IRAC 11A",
    # Fungicidas (FRAC)
    "azoxistrobina": "FRAC 11",
    "piraclostrobina": "FRAC 11",
    "trifloxistrobina": "FRAC 11",
    "kresoxim": "FRAC 11",
    "fluopyram": "FRAC 7",
    "fluopiram": "FRAC 7",
    "fluxapiroxad": "FRAC 7",
    "boscalid": "FRAC 7",
    "propiconazol": "FRAC 3",
    "difenoconazol": "FRAC 3",
    "tebuconazol": "FRAC 3",
    "ciproconazol": "FRAC 3",
    "fenbuconazol": "FRAC 3",
    "metalaxil": "FRAC 4",
    "mandipropamida": "FRAC 40",
    "dimetomorf": "FRAC 40",
    "ciazofamida": "FRAC 21",
    "ametoctradina": "FRAC 45",
    "fluazinam": "FRAC 29",
    "fenhexamida": "FRAC 17",
    "ciprodinil": "FRAC 9",
    "fludioxonil": "FRAC 12",
    "fosetil-aluminio": "FRAC P07",
    "fosetil": "FRAC P07",
    "fosfito": "FRAC P07",
    "mancozeb": "FRAC M03",
    "metiram": "FRAC M03",
    "captan": "FRAC M04",
    "folpet": "FRAC M04",
    "clorotalonil": "FRAC M05",
    "oxicloruro de cobre": "FRAC M01",
    "hidroxido de cobre": "FRAC M01",
    "azufre": "FRAC M02",
}


# Nombres COMERCIALES → ingrediente(s) activo(s). En finca nadie pide "clorpirifos": pide la marca
# del almacén. Sin esto, el guardarraíl de prohibidos/destino/IRAC/cat-tox NO se activaba (la
# detección era por subcadena del nombre químico). NO exhaustivo y los registros cambian: VERIFICA
# siempre la etiqueta. Lo crítico aquí son las marcas que mapean a un i.a. PROHIBIDO/RESTRINGIDO
# (Gramoxone→paraquat, Furadan→carbofurán, Thiodan→endosulfán, Lorsban→clorpirifos).
COMMERCIAL_NAMES: dict[str, tuple[str, ...]] = {
    # Prohibidos/restringidos por su marca (backstop de seguridad)
    "gramoxone": ("paraquat",),
    "gramuron": ("paraquat",),
    "furadan": ("carbofuran",),
    "thiodan": ("endosulfan",),
    "lorsban": ("clorpirifos",),
    "pyrinex": ("clorpirifos",),
    "lannate": ("metomilo",),
    # Insecticidas/acaricidas modernos por marca
    "engeo": ("tiametoxam", "lambda-cialotrina"),
    "actara": ("tiametoxam",),
    "confidor": ("imidacloprid",),
    "coragen": ("clorantraniliprol",),
    "benevia": ("ciantraniliprol",),
    "verimark": ("ciantraniliprol",),
    "exirel": ("ciantraniliprol",),
    "movento": ("spirotetramat",),
    "vertimec": ("abamectina",),
    "agrimec": ("abamectina",),
    "oberon": ("spiromesifen",),
    "rimon": ("novaluron",),
    # Herbicidas
    "roundup": ("glifosato",),
    "round-up": ("glifosato",),
    # Fungicidas por marca
    "manzate": ("mancozeb",),
    "dithane": ("mancozeb",),
    "amistar": ("azoxistrobina",),
    "bankit": ("azoxistrobina",),
    "cabrio": ("piraclostrobina",),
    "aliette": ("fosetil-aluminio",),
    "ridomil": ("metalaxil", "mancozeb"),
    "sercadis": ("fluxapiroxad",),
    "revus": ("mandipropamida",),
    "kocide": ("hidroxido de cobre",),
}
# Nota: se omiten marcas cuyo nombre es palabra común (Basta, Muralla, Luna, Score, Match, Tilt,
# Switch, Closer, Tracer…) para no producir falsos positivos por coincidencia léxica.


def extract_active_ingredient(text: str) -> str | None:
    """Primer ingrediente activo del texto (orden determinista: nombre químico por orden de la
    tupla; si no hay, primer i.a. por marca comercial)."""
    low = text.lower()
    direct = next((ia for ia in ACTIVE_INGREDIENTS if ia in low), None)
    if direct is not None:
        return direct
    for brand, actives in COMMERCIAL_NAMES.items():
        if re.search(rf"\b{re.escape(brand)}\b", low):
            return actives[0]
    return None


def commercial_actives_in(text: str) -> set[str]:
    """Ingredientes activos detectados por NOMBRE COMERCIAL (marca), con límite de palabra."""
    low = text.lower()
    out: set[str] = set()
    for brand, actives in COMMERCIAL_NAMES.items():
        if re.search(rf"\b{re.escape(brand)}\b", low):
            out.update(actives)
    return out


def active_ingredients_in(text: str) -> set[str]:
    """Todos los ingredientes activos presentes, por nombre QUÍMICO o por marca comercial."""
    low = text.lower()
    found = {ia for ia in ACTIVE_INGREDIENTS if ia in low}
    found |= commercial_actives_in(text)
    return found


def mode_of_action_groups(text: str) -> dict[str, str]:
    """Mapa {i.a. -> grupo IRAC/FRAC} de los activos reconocidos en el texto (los que tienen grupo)."""
    return {ia: MODE_OF_ACTION_GROUP[ia] for ia in active_ingredients_in(text) if ia in MODE_OF_ACTION_GROUP}


# Agentes de CONTROL BIOLÓGICO (parasitoides, depredadores, entomopatógenos) — pilar del MIP de
# exportación, que el comprador (GlobalGAP) exige y el motor químico-céntrico ignoraba. Se reconocen
# para NO tratarlos como químicos y para nudge "biológico/cultural antes del químico". NO exhaustivo.
BENEFICIAL_AGENTS: tuple[str, ...] = (
    "trichogramma", "amblyseius", "neoseiulus", "phytoseiulus", "galendromus", "typhlodromus",
    "chrysoperla", "orius", "encarsia", "eretmocerus", "cryptolaemus", "stethorus",
    "beauveria", "metarhizium", "bacillus thuringiensis", "paecilomyces", "lecanicillium",
    "isaria", "cordyceps", "steinernema", "heterorhabditis",
    "parasitoide", "depredador", "entomopatogeno", "control biologico", "biocontrol",
    "acaro depredador", "avispa parasitica", "fauna auxiliar", "enemigo natural",
)


def beneficials_in(text: str) -> set[str]:
    """Agentes de control biológico mencionados en el texto (sin tildes, por subcadena)."""
    low = _noacc(text)
    return {b for b in BENEFICIAL_AGENTS if b in low}


def mentions_biocontrol(text: str) -> bool:
    """True si el texto menciona control biológico (parasitoides/depredadores/entomopatógenos)."""
    return bool(beneficials_in(text))


# Plagas de CONTROL OFICIAL / cuarentenarias del aguacate en Colombia (Resolución ICA 1507/2016).
# Su régimen es de TOLERANCIA CERO / admisibilidad (monitoreo + reporte al ICA + control de
# movilización + área libre para exportar), NO un umbral económico. Reconocerlas para avisar del régimen.
QUARANTINE_PESTS: tuple[str, ...] = (
    "stenoma catenifer", "stenoma", "heilipus lauri", "heilipus trifasciatus", "heilipus",
    "barrenador del fruto", "barrenador de la semilla",
)


def quarantine_pests_in(text: str) -> list[str]:
    """Plagas de control oficial (cuarentenarias) mencionadas en el texto (sin tildes, por subcadena)."""
    low = _noacc(text)
    hits = [p for p in QUARANTINE_PESTS if p in low]
    # Evita redundancia "heilipus" + "heilipus lauri": deja el nombre más específico.
    return [p for p in hits if not any(p != o and p in o for o in hits)]
