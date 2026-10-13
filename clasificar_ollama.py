"""Clasifica incidencias con un modelo local (Ollama) y guarda los resultados.

Uso:
  python clasificar_ollama.py datos/validacion_sintetica.json resultados_validacion.json [modelo]

Sin dependencias externas (solo biblioteca estándar). Salida estructurada con esquema JSON
para que el resultado se pueda validar. El modelo es configurable: la variable
OLLAMA_URL permite apuntar a cualquier servidor compatible; no hay claves en el código.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

URL = os.environ.get("OLLAMA_URL", "http://127.0.0.1:11434") + "/api/chat"
MODELO_DEFECTO = "qwen2.5:3b-instruct"

SISTEMA = """Eres un asistente de operaciones de rampa de un aeropuerto. Clasifica cada incidencia.
Tipos: equipaje, carga_balance, equipo_gse, seguridad_prl, personal, documentacion, otro.
Gravedad:
- critica: riesgo para personas o para la seguridad de la aeronave (fuego, derrame peligroso, zona de hélices, mercancía peligrosa sin documentación).
- alta: retraso notable (10 minutos o más), daño material relevante, lesión de una persona o incumplimiento de seguridad.
- media: incidencia gestionada sin retraso que afecta al proceso.
- baja: informativa o sin impacto.
aprobacion es true si la gravedad es alta o critica, y false en otro caso.
Responde solo con el JSON pedido."""

ESQUEMA = {
    "type": "object",
    "properties": {
        "tipo": {"type": "string", "enum": ["equipaje", "carga_balance", "equipo_gse", "seguridad_prl", "personal", "documentacion", "otro"]},
        "gravedad": {"type": "string", "enum": ["baja", "media", "alta", "critica"]},
        "aprobacion": {"type": "boolean"},
    },
    "required": ["tipo", "gravedad", "aprobacion"],
}


def clasificar(texto: str, modelo: str) -> dict:
    cuerpo = {
        "model": modelo,
        "stream": False,
        "format": ESQUEMA,
        "options": {"temperature": 0},
        "messages": [
            {"role": "system", "content": SISTEMA},
            {"role": "user", "content": texto},
        ],
    }
    req = urllib.request.Request(URL, data=json.dumps(cuerpo).encode(), headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(json.loads(r.read())["message"]["content"])


def main() -> None:
    if len(sys.argv) < 3:
        sys.exit(__doc__)
    casos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    modelo = sys.argv[3] if len(sys.argv) > 3 else MODELO_DEFECTO
    salida = []
    for c in casos:
        try:
            r = clasificar(c["texto"], modelo)
        except Exception as e:  # una incidencia nunca se pierde: se registra el fallo
            r = {"tipo": None, "gravedad": None, "aprobacion": None, "error": str(e)}
        r["id"] = c["id"]
        salida.append(r)
    Path(sys.argv[2]).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(salida)} incidencias clasificadas con {modelo} -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
