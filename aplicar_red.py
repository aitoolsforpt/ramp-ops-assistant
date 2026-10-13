"""Aplica la red de seguridad a un fichero de resultados del modelo.

Uso: python aplicar_red.py datos/validacion_sintetica.json resultados/llm7b_validacion.json resultados/llm7b_red_validacion.json
"""
import json
import sys
from pathlib import Path

from red_seguridad import aplicar


def main() -> None:
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    casos = {c["id"]: c for c in json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))}
    res = json.loads(Path(sys.argv[2]).read_text(encoding="utf-8"))
    out = []
    for r in res:
        nuevo = aplicar(casos[r["id"]]["texto"], r)
        nuevo["id"] = r["id"]
        out.append(nuevo)
    Path(sys.argv[3]).write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(out)} resultados con red de seguridad -> {sys.argv[3]}")


if __name__ == "__main__":
    main()
