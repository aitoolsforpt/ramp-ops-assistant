"""Red de seguridad: ninguna incidencia con señales de riesgo pasa sin revisión humana.

Se aplica DESPUÉS del modelo. Si el texto contiene señales críticas o altas y el modelo
no lo ha marcado, se sube la gravedad y se exige aprobación. Prefiere un falso aviso a
dejar pasar un caso grave. Las señales salen del contrato de etiquetas (README), no de
los casos de prueba. El mismo criterio está implementado en el nodo de n8n (workflow.json).
"""
import re

CRITICAS = re.compile(
    r"\b(fuego|humo|llamas?|incendio|combustible|derrame|fuga|peligros[ao]|h[eé]lices?|atrapad[oa]|"
    r"herid[oa]s?|lesi[oó]n|quemadura|desmay\w*|colisi[oó]n|choque|explosi\w*)\b",
    re.IGNORECASE,
)
ALTAS = re.compile(
    r"(sin chaleco|sin formaci[oó]n|formaci[oó]n vigente|cable pelado|exceso de peso|desequilibr\w*|"
    r"peso (distinto|inferior|superior)|resbal\w*|impact\w*|dolor de espalda|sin protectores|sin autorizaci[oó]n"
    r"|(?:bodega|puerta|compuerta|escotilla)[^.;]{0,40}(?:sin cerrar|sin asegurar|mal cerrad\w*|no cierra))",
    re.IGNORECASE,
)
MINUTOS = re.compile(
    r"(?:retras\w*[^.;]{0,60}?(\d+)\s*minutos|(\d+)\s*minutos\s*(?:de\s*)?(?:retraso|tarde))",
    re.IGNORECASE,
)
ORDEN = ["baja", "media", "alta", "critica"]


def _retraso_minutos(texto: str) -> int:
    m = MINUTOS.search(texto)
    if not m:
        return 0
    return int(m.group(1) or m.group(2))


def aplicar(texto: str, r: dict) -> dict:
    """Devuelve una copia de r con la red de seguridad aplicada y una lista de motivos."""
    out = dict(r)
    motivos = []
    piso = None
    if CRITICAS.search(texto):
        piso, motivos = "critica", ["señal crítica en el texto"]
    elif ALTAS.search(texto) or _retraso_minutos(texto) >= 10:
        piso, motivos = "alta", ["señal alta o retraso ≥ 10 min"]
    if piso and (out.get("gravedad") not in ORDEN or ORDEN.index(out["gravedad"]) < ORDEN.index(piso)):
        out["gravedad"] = piso
    if out.get("gravedad") in ("alta", "critica"):
        out["aprobacion"] = True
    if out.get("gravedad") not in ORDEN or out.get("tipo") is None:
        out["aprobacion"] = True  # respuesta inválida del modelo: revisión humana
        motivos.append("respuesta inválida del modelo")
    out["motivos_seguridad"] = motivos
    return out
