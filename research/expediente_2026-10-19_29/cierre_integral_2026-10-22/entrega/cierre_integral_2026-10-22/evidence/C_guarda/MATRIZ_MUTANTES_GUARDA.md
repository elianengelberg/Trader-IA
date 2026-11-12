# Matriz de mutantes de la guarda 05: v1 (paquete `410ae629`) frente a v2 (esta misión)

- **Qué se corrió:** 26 casos por versión, sobre los árboles de la extracción limpia de v3r3; cada caso es una copia aislada con UN cambio.
- **«Razón correcta»:** la aserción que falla contiene el texto previsto para ese defecto, por ejemplo «sent again after it was dead» para D1 o «growth_after_close» para D3. Así se comprueba que la prueba detecta el defecto introducido y no otra cosa.
- **Pruebas:** D1c, D2, D3p, D3r y Tj son las 5 de comportamiento; chk y ver son las 2 de autocomprobación. En total, 7.

| Caso | Árbol | Cambio | Esperado | v1 | Fallan (v1) | v2 | Fallan (v2) | Razón exigida |
|---|---|---|---|---|---|---|---|---|
| N0_obligatoria | obligatoria | control positivo: 01+02v3 | pasa | OK | — | OK | — | — |
| N1_02v3_sin_01 | solo02v3 | etiqueta 1.1.0 sin D1-D3 | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «sent again after it was dead»; D2: «no stop in the book ever moved» |
| N2_base_con_guarda_B_sin_A | base | B sin A: la guarda sin 01+02v3 | falla | VIVO | — | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «no engine_version» |
| N3_01_sin_02v3_reversion_parcial | solo01 | A revertida a medias: 02v3 revertido solo (R4) | falla | VIVO | — | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «no engine_version» |
| M1_D1_salida_id_sin_barra | obligatoria | D1 cierres: el reintento reusa el id del cierre rechazado | falla | OK (detectado, razón correcta) | D1c,D3r,Tj | OK (detectado, razón correcta) | D1c,D3r,Tj | D1c: «market» |
| M2_D1_stop_id_sin_colocacion | obligatoria | D1 stops: la recolocación reusa el id del stop cancelado | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «stop» |
| M3_D2_sin_comparar_nivel | obligatoria | D2 | falla | OK (detectado, razón correcta) | D2 | OK (detectado, razón correcta) | D2 | D2: «no stop in the book ever moved» |
| M4_D3_sin_cancelar_resto_al_salir | obligatoria | D3 capa 1 | falla | OK (detectado, razón correcta) | D3p,D3r | OK (detectado, razón correcta) | D3p,D3r | D3p: «growth_after_close» |
| M5_D3_sin_cancelar_resto_en_plano | obligatoria | D3 capa 2 | falla | OK (detectado, razón correcta) | D3p | OK (detectado, razón correcta) | D3p | D3p: «entries_filling_a_later_position» |
| M6_D3_sin_red_de_seguridad | obligatoria | D3 capa 3 | falla | OK (detectado, razón correcta) | D3r | OK (detectado, razón correcta) | D3r | D3r: «uncovered_streaks» |
| M7_sin_aviso_de_pierna_sin_stop | obligatoria | aviso del informe, no regla de venue (lo cubre 01) | fuera de alcance | no detectado | — | no detectado | — | — |
| M8_D3_sin_ninguna_capa | obligatoria | D3 entero | falla | OK (detectado, razón correcta) | D3p,D3r | OK (detectado, razón correcta) | D3p,D3r | D3p: «growth_after_close» |
| M9_D2_recoloca_el_stop_en_cada_barra | obligatoria | D2 sin recolocaciones de más | falla | OK (detectado, razón correcta) | D2 | OK (detectado, razón correcta) | D2 | D2: «replaced at the same size and level» |
| M10_cierre_sin_reduce_only | obligatoria | regla previa que 1.1.0 no debilita | falla | OK (detectado, razón correcta) | D1c,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D3p,D3r,Tj | D3p: «without reduce_only» |
| E1_02v3_sin_01_con_contadores_falsos | solo02v3 | evasión: interfaz de 01 sin comportamiento | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «sent again after it was dead» |
| E2_02v3_sin_01_con_resting_orders | solo02v3 | evasión: método de 01 sin usarlo | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «sent again after it was dead» |
| C1_cierre_limite_reduce_only | obligatoria | otra implementación válida del cierre: límite agresiva reduce-only | pasa | MAL | D1c,D3r | OK | — | — |
| C2_02v3_sin_01_cierre_limite | solo02v3 | otra forma de cierre sin D1-D3 | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D2: «no stop in the book ever moved» |
| L1_obligatoria_1_0_9 | obligatoria | no promete D1-D3 | se omite | OK | — | OK | — | — |
| L2_02v3_sin_01_1_0_9 | solo02v3 | etiqueta veraz | se omite | OK | — | OK | — | — |
| L3_obligatoria_1_2_0 | obligatoria | versión posterior | pasa | OK | — | OK | — | — |
| L4_02v3_sin_01_1_2_0 | solo02v3 | posterior sin D1-D3 | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «sent again after it was dead» |
| L5_obligatoria_1_1_0_dev | obligatoria | ilegible: falla cerrado | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «not a dotted number» |
| L6_02v3_sin_01_1_1 | solo02v3 | forma corta = 1.1.0 | falla | VIVO | — | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «sent again after it was dead» |
| L7_obligatoria_1_1 | obligatoria | forma corta = 1.1.0 | pasa | MAL | — | OK | — | — |
| L8_obligatoria_v1_1_0 | obligatoria | prefijo v: ilegible | falla | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | OK (detectado, razón correcta) | D1c,D2,D3p,D3r,Tj | D1c: «not a dotted number» |

**Resumen.**
- **v1:** 20 de 26 dan lo esperado (más M7, fuera de alcance). Defectos demostrados:
  - N2 (B sin A), N3 (02v3 revertido solo) y L6 («1.1» sin D1–D3) quedan VIVOS: la guarda se omite;
  - L7 («1.1» con D1–D3) se omite en vez de exigir;
  - C1 (cierre límite reduce-only, una implementación válida) da un FALSO POSITIVO.
- **v2:** 25 de 26 dan lo esperado (la restante es M7, fuera de alcance por diseño), todos los detectados por la razón correcta. M7 queda fuera de alcance por diseño: es un aviso del informe, no una regla de la venue, y lo cubre la prueba de 01.
