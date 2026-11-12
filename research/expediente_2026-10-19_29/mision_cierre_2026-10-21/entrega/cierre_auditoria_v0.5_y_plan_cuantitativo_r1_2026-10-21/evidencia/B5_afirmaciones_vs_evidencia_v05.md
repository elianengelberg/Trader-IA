| Afirmación | Declarado | Observado | ¿Coincide? | Nota |
|---|---|---|---|---|
| C01 suite completa | 449 passed, 0 failed | 449 passed | sí |  |
| C02 estabilidad | 3 corridas de 130 | 3 corridas: ['130', '130', '130'] | sí |  |
| C03 matriz antes/después | 48 de 48 filas con el patrón | 48 de 48 filas «sí» | sí |  |
| C04 mutaciones P2 | 11 de 11 | 11 de 11 detectadas (MUERTA) | sí |  |
| C05 mutaciones de la cadena | 20 de 20 | 20 de 20 detectadas (MUERTA) | sí |  |
| C06 mutaciones de durabilidad | 4 de 4 | 4 de 4 detectadas (MUERTA) | sí |  |
| C07 mutaciones del ejecutor | 10 de 10 | 10 de 10 detectadas (MUERTA) | sí |  |
| C08 tabla de decisión de P2 | 86.400 de 86.400 | Coinciden con el oráculo independiente: 86400 de 86400 | sí |  |
| C09 Ed25519 diferencial | 807 casos; propia rechaza toda clave/R degenerada; OpenSSL acepta 34/128 y 7/40 | 807 casos; propia acepta 0 degeneradas; OpenSSL 34/128 y 7/40 | sí |  |
| C10 corte de energía simulado | 102 escenarios por código, 0 violaciones | [('det', 102, 0), ('nodet', 102, 0)] | sí |  |
| C11 fallos de escritura | 72 escenarios por código, 0 violaciones | [('det', 72, 0), ('nodet', 72, 0)] | sí |  |
| C12 pruebas recogidas | 449 (= C01) | 449 | sí |  |
| C13 pruebas del ejecutor aislado | 32 | 32 | sí |  |
| C14 escenarios cruzados | X1–X26 | 23 en nombres de prueba + [19] solo en comentarios; faltan [10, 17] | **NO** | X10 y X17 no existen en ninguna versión (v0.3–v0.5): la numeración salta. Imprecisión de documentación (D-3): son 24 escenarios, no 26 |
| C15 oráculo P1 (estados) | 720 combinaciones | 720 | sí |  |
| C16 oráculo P1 (recibos ligados) | 80 combinaciones | 80 = DECL×RESERVA×CORRUPCION | sí |  |
| C17 oráculo P1 (reproducción) | 210 combinaciones | 210 = VIA×REPRO_DECL×RESERVA_REPRO×CONTENIDO | sí |  |
| C18 fuzzing P1 | 300 mutaciones aleatorias | range(300) | sí |  |
| C19 mutaciones aleatorias P4 | 120 | 60 casos × 2 códigos | sí |  |
| C20 suite de v0.4 sin modificar | 350 pasan, 9 fallan (deliberadas) | 9 failed, 350 passed; lista: 9 | sí |  |
| C21 suite P4 de v0.3 sin modificar | 112 pasan | 112 passed | sí |  |
| C22 parches 0001–0007 | aplican y la suite pasa en HEAD y origin exportados | 2 aplicaciones OK; 2 suites OK | sí |  |
| C23 estado real de T | INCONCLUSO (SIN_REFERENCIA_INDEPENDIENTE); P2 NO_CANDIDATA | INCONCLUSO ['SIN_REFERENCIA_INDEPENDIENTE']; P2 NO_CANDIDATA | sí |  |
| C24 entregas anteriores | 5 de 5 OK | 5 OK | sí |  |
| C25 estado de git | antes == después; huella 87b9585d… | 87b9585d31924f81… | sí |  |
| C26 paquete intacto (etapa 13) | sin cambios ni archivos nuevos | paquete intacto: sin cambios ni archivos nuevos (p. ej. __pycache__) | sí | Límite D-1: la etapa 13 de v0.5 no mira enlaces ni directorios vacíos |
| C27 estilo (ruff) | sin hallazgos | All checks passed! | sí |  |

26 de 27 afirmaciones coinciden con lo observable
salida: 1 (1 = hay discrepancias; se esperan exactamente las documentadas: C14/D-3)
