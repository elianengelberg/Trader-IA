# Adenda R · corrección opcional R1′: alcance por clase, no por las listas filtradas de cada lunes

**Estado:** PROPUESTA OPCIONAL, congelada **después** de calcular P0 con la regla R1 literal y **antes** de calcular cualquier retorno. Solo rige si se elige expresamente antes de la ejecución confirmatoria. Si no se elige, rige R1 tal como quedó congelada.

## Qué corrige
- La R1 congelada dice que un par está fuera de alcance si figura en `lista_fija` o `apalancados` del último lunes ≤ L (o ≤ E).
- Esas listas por lunes **no** son la clase de §4.5. Son el subconjunto de esa clase que ya pasó los filtros de actividad de 30 días, edad de 180 días y liquidez. Un token apalancado que dejó de cotizar antes de esa fecha, o que nunca fue líquido, no aparece en ellas.
- **Consecuencia observada en P0** (sin retornos): DOTUP, DOTDOWN y TRXDOWN (falla T, E = 2023-04-27) quedaron «en alcance». Eso fija (ii′) en 2023-05-01 y H en 160 semanas.
- La intención escrita en la propia R1 («esos pares nunca son elegibles, §4.5») es otra: excluir **clases** que la v3 excluye siempre.
- El defecto es mío: no verifiqué la semántica de las listas antes de congelar.

## R1′
Un par está **fuera de alcance** si se da cualquiera de estas condiciones:
- (a) su base está en la lista fija de §4.5: USDC, BUSD, TUSD, USDP, PAX, DAI, FDUSD, USDS, USDSB, UST, USTC, SUSD, PAXG, XAUT, AEUR, EURI, USD1, BIDR, IDRT y BVND, o es un código ISO-4217 de moneda fiat;
- (b) su base es X + {UP, DOWN, BULL, BEAR}, con X la base de otro par USDT del listado del bucket (la definición de §4.5);
- (c) figura en `lista_fija` o `apalancados` de **algún** lunes (es decir, R1 sigue aplicándose: R1′ solo agrega exclusiones por clase, nunca quita).

Todo lo demás de la Adenda R queda igual.

## Por qué la presento y qué no hago
- **No reemplazo la regla congelada:** el resultado oficial de P0 es el de R1 literal (VÁLIDO, 160 semanas).
- **Por qué la presento:** la ventana más larga casi duplica la información de H1 sobre el tamaño de efecto que importa económicamente (IC ≈ 0,02; `P0d_potencia_H1_segun_ventana.txt`). Y la elección entre las dos sigue siendo ciega al resultado: nadie calculó un retorno, un IC ni una relación entre señal y resultado.
- **El riesgo que tiene elegirla:** sienta el precedente de corregir una regla después de ver qué hace con la ventana. Por eso queda escrita, congelada, con su motivo y su resultado, y requiere tu elección expresa.
