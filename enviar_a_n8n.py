"""Envía un conjunto de incidencias al workflow de n8n y guarda las respuestas.

Uso: python enviar_a_n8n.py datos/validacion_sintetica.json resultados/n8n_validacion.json

Requiere n8n en marcha con el workflow publicado (webhook /webhook/incidencia).
Variable N8N_URL para cambiar el servidor. Solo biblioteca estándar.
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

URL = os.environ.get("N8N_URL", "http://127.0.0.1:5678") + "/webhook/incidencia"


def enviar(caso: dict) -> dict:
    cuerpo = json.dumps({"id": caso["id"], "texto": caso["texto"]}).encode()
    req = urllib.request.Request(URL, data=cuerpo, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=600) as r:
        return json.loads(r.read())


def main() -> None:
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    casos = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    salida = []
    for c in casos:
        try:
            r = enviar(c)
        except Exception as e:
            r = {"tipo": None, "gravedad": None, "aprobacion": None, "error": str(e)}
        r["id"] = c["id"]
        salida.append(r)
    Path(sys.argv[2]).write_text(json.dumps(salida, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(salida)} incidencias procesadas por n8n -> {sys.argv[2]}")


if __name__ == "__main__":
    main()
