# E3 · Adenda R2: cortes con salto de precio sin mapeo

**Estado:** PROPUESTA, congelada antes de calcular cualquier retorno. Forma parte del paquete «v3 + Adenda R», con o sin la corrección R1′. **No autoriza ninguna ejecución.**

## Problema (sin retornos: lista estructural de F3, `estructural.json` → `cortes_con_reanudacion.lista_saltos`)
- La Adenda 1 exige mapear con anuncio los renombres y las redenominaciones. Sin anuncio, rige la regla de 30 días: un corte de menos de 30 días se lee como **el mismo listado**.
- La lectura manual de renombres (A3.11) nunca se hizo, así que **no hay ningún mapeo congelado**.
- Hay cortes de 1 a 18 días tras los cuales el precio salta ×10 o más, en cualquier sentido. Dentro de las ventanas posibles, sin contar los tokens apalancados (que nunca son elegibles):
  - con inicio 2023-05-01: QUICK (×0,001) y STRAX (×0,1);
  - con inicio 2021-02-22, además: DREP (×100), SUN (×0,001), LUNA (×3125), VIDT (×0,1) y BNX (×0,01).
- **En H1** el efecto está acotado:
  - la señal no puede cruzar el corte, porque la elegibilidad exige 30 días activos seguidos;
  - el resultado de esa semana es un único rango extremo entre ~100.
- **En H2**, una posición tenida a través del corte se valúa al precio del activo nuevo. Eso es un retorno ficticio de −99,9 % o de ×3125 en una sola moneda, que puede dominar el exceso de toda la ventana.

## Regla
**R2.1** Un corte con reanudación se trata como **fin del listado más listado nuevo** si cumple todo esto:
- figura en la lista estructural congelada de F3;
- tiene |log₁₀(precio de reanudación / último precio)| ≥ 1;
- no tiene un mapeo congelado (hoy no hay ninguno).

**R2.2** En el panel, la serie se parte en el día de reanudación:
- el tramo anterior termina en el último día activo; después aplica la regla de inactividad de la v3 (liquidación contable al último precio negociado tras 30 días inactivos, §4.10);
- el tramo posterior es otro símbolo, con edad desde cero (§4.4 b).
- El nuevo símbolo conserva el sufijo `USDT`, y su base se rotula con un prefijo para que no coincida con ninguna base existente. Los tokens apalancados no se parten: ya están excluidos.

**R2.3** Sin cambios: el resto de la v3, la Adenda R y R1′.

## Por qué así
- Es la regla 1 de la Adenda 1 («si X vuelve, ese tramo es un listado nuevo») aplicada sin anuncio, con un criterio mecánico que no depende del resultado.
- Es conservadora: la posición se liquida al último precio del activo viejo, sin ganancia ni pérdida ficticia.
- **La alternativa,** dejarlo como «limitación informada» como pedía la regla 3 de la Adenda 1, deja que un solo evento ficticio decida H2. Esa regla se escribió suponiendo que habría mapeos con anuncio; sin ellos, ya no protege.

## Contaminación declarada
- Se conocen los cortes, sus fechas y sus relaciones de precio: datos estructurales de F3, sin retornos de estrategia.
- **No se conoce** si la cartera tendría alguno de esos símbolos en la semana del corte, ni ningún retorno, IC o exceso.
- La regla no puede elegirse para favorecer un resultado, porque nadie sabe qué resultado produce.
