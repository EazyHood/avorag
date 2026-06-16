"""Conocimiento de dominio agronómico, sin dependencias de infraestructura."""

from __future__ import annotations

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


def extract_active_ingredient(text: str) -> str | None:
    """Primer ingrediente activo conocido que aparece en el texto (o None)."""
    low = text.lower()
    return next((ia for ia in ACTIVE_INGREDIENTS if ia in low), None)


def active_ingredients_in(text: str) -> set[str]:
    """Todos los ingredientes activos conocidos presentes en el texto."""
    low = text.lower()
    return {ia for ia in ACTIVE_INGREDIENTS if ia in low}


def mode_of_action_groups(text: str) -> dict[str, str]:
    """Mapa {i.a. -> grupo IRAC/FRAC} de los activos reconocidos en el texto (los que tienen grupo)."""
    return {ia: MODE_OF_ACTION_GROUP[ia] for ia in active_ingredients_in(text) if ia in MODE_OF_ACTION_GROUP}
