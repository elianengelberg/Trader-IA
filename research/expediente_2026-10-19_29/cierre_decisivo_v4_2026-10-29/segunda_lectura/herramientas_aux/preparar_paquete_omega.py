"""Auxiliar (posterior a la congelación de SL-v1; solo empaqueta, no decide): copia al paquete de la segunda ronda las
páginas de los candidatos Ω, verificadas por hash, y una lista ciega de candidatos (par, archivo, contexto, etiquetas).
No agrega fechas de pasadas anteriores, categorías ni nada de la ventana.
Uso: python3 -I -B preparar_paquete_omega.py <dir_paginas> <candidatos_omega.json> <dir_paquete_omega>"""
import hashlib
import json
import shutil
import sys
from pathlib import Path

PAG, CAND, OUT = (Path(a) for a in sys.argv[1:4])
lista = json.loads(CAND.read_text())["lista"]
(OUT / "paginas").mkdir(parents=True, exist_ok=False)
hashes = {}
for c in lista:
    f = c["archivo"]
    if f not in hashes:
        h = hashlib.sha256((PAG / f).read_bytes()).hexdigest()
        assert h == c["sha256_pagina"]
        shutil.copyfile(PAG / f, OUT / "paginas" / f)
        assert hashlib.sha256((OUT / "paginas" / f).read_bytes()).hexdigest() == h
        hashes[f] = h
ciegos = [{"id": f"O{n:03d}", "par": c["par"], "archivo": c["archivo"], "etiquetas_escaneo": c["etiquetas"], "contexto": c["contexto"]}
          for n, c in enumerate(sorted(lista, key=lambda c: (c["archivo"], c["par"])), 1)]
(OUT / "CANDIDATOS.json").write_text(json.dumps(ciegos, ensure_ascii=False, indent=1))
(OUT / "PAGINAS.sha256").write_text("".join(f"{h}  paginas/{f}\n" for f, h in sorted(hashes.items())))
print(json.dumps({"candidatos": len(ciegos), "paginas": len(hashes)}))
