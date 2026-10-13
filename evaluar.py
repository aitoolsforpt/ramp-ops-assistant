"""Evalúa un clasificador de incidencias contra el conjunto sintético.

Uso:
  python evaluar.py baseline            # evalúa el clasificador de reglas incluido
  python evaluar.py resultados.json     # evalúa las salidas de otro sistema (n8n + LLM)
  python evaluar.py baseline datos/validacion_sintetica.json   # contra otro conjunto de casos

El fichero de resultados es una lista de objetos {"id", "tipo", "gravedad", "aprobacion"}.
Solo usa la biblioteca estándar. Datos ficticios: ver datos/incidentes_sinteticos.json.
"""
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path

AQUI = Path(__file__).parent
DATOS = AQUI / "datos" / "incidentes_sinteticos.json"

REGLAS_TIPO = [
    ("seguridad_prl", ["chaleco", "combustible", "espalda", "resbala", "impacta", "carenado", "formación vigente", "heridos"]),
    ("equipo_gse", ["tractor", "gpu", "escalera", "carrito", "báscula", "bascula", "pesaje"]),
    ("carga_balance", ["contenedor", "uld", "distribución de carga", "exceso de peso", "retraso de 25", "bodega"]),
    ("documentacion", ["manifiesto", "parte de turno", "hoja de carga", "documentación", "mercancía peligrosa"]),
    ("personal", ["falta una persona", "faltan dos operarios", "acreditación", "baja de última hora"]),
    ("equipaje", ["maleta", "equipaje", "etiqueta"]),
]
PALABRAS_CRITICA = ["combustible", "carenado", "mercancía peligrosa"]
PALABRAS_ALTA = ["retraso de", "sin chaleco", "espalda", "resbala", "impacta", "cable pelado", "formación vigente", "exceso de peso", "peso distinto", "faltan dos operarios"]


def baseline(texto: str) -> dict:
    t = texto.lower()
    tipo = "otro"
    for nombre, claves in REGLAS_TIPO:
        if any(c in t for c in claves):
            tipo = nombre
            break
    if any(p in t for p in PALABRAS_CRITICA):
        gravedad = "critica"
    elif any(p in t for p in PALABRAS_ALTA):
        gravedad = "alta"
    elif tipo in ("equipo_gse", "personal", "documentacion", "carga_balance"):
        gravedad = "media"
    else:
        gravedad = "baja"
    return {"tipo": tipo, "gravedad": gravedad, "aprobacion": gravedad in ("alta", "critica")}


def cargar_resultados(arg: str, casos: list) -> dict:
    if arg == "baseline":
        return {c["id"]: baseline(c["texto"]) for c in casos}
    datos = json.loads(Path(arg).read_text(encoding="utf-8"))
    return {d["id"]: d for d in datos}


def main() -> None:
    if len(sys.argv) not in (2, 3):
        sys.exit(__doc__)
    datos = Path(sys.argv[2]) if len(sys.argv) == 3 else DATOS
    casos = json.loads(datos.read_text(encoding="utf-8"))
    res = cargar_resultados(sys.argv[1], casos)
    campos = ["tipo", "gravedad", "aprobacion"]
    aciertos = Counter()
    errores = defaultdict(list)
    falta = 0
    for c in casos:
        r = res.get(c["id"])
        if r is None:
            falta += 1
            continue
        for campo in campos:
            if r.get(campo) == c[campo]:
                aciertos[campo] += 1
            else:
                errores[campo].append((c["id"], c[campo], r.get(campo)))
    n = len(casos)
    print(f"Casos: {n}  sin respuesta: {falta}")
    for campo in campos:
        print(f"  {campo:11s} {aciertos[campo]:2d}/{n} = {aciertos[campo] / n:.0%}")
    # El error grave: una incidencia que exigía aprobación humana y se dejó pasar.
    graves = [e for e in errores["aprobacion"] if e[1] is True and e[2] is False]
    print(f"Incidencias que exigían aprobación y se dejaron pasar: {len(graves)}")
    for campo in campos:
        for id_, esperado, obtenido in errores[campo]:
            print(f"    {id_} {campo}: esperado={esperado} obtenido={obtenido}")


if __name__ == "__main__":
    main()
