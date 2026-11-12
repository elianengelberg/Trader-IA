# E3: limitaciones estadísticas registradas al congelar la v3 (antes de los datos)

1. **El control del error de familia del 5 % es nominal.** Depende de que p₁, p₂ y p₃ sean valores p válidos bajo sus nulas (v3, Anexo A, supuesto S1).
   - p₁ es asintótico (Newey–West).
   - p₂ y p₃ son de bootstrap-t por bloques.
   - El error real es ≤ 5 % más la distorsión de tamaño de esos valores p.
2. **La calibración sintética no demuestra validez en los datos reales.**
   - Solo muestra que el código es correcto y que el tamaño es cercano al nominal en cinco procesos elegidos de antemano (colas pesadas, AR(1), GARCH y asimetría), con n = 340 y bloques de 13.
   - El diagnóstico con carteras aleatorias es evidencia parcial, porque su media nula es aproximada.
3. **La potencia de H2 es analítica y depende de supuestos no verificados.**
   - **Valor:** 0,11–0,17 al 0,025 y 0,18–0,26 al 0,05, frente a una ventaja neta real del 10 %/año.
   - **Supuestos:** tracking error de 25–35 %/año; 6,5–7 años; excesos semanales independientes y casi normales; ventaja constante.
   - **Fuera del cálculo:** la robustez, el requisito de H1 y el posible recorte de la ventana por supervivencia, que solo pueden bajarla.
4. **La historia no es fuera de muestra:** quienes diseñan conocen el período y BTC y ETH se reutilizan. Un resultado favorable es «evidencia histórica», no una confirmación independiente.
5. **Ninguna clasificación autoriza capital.** El experimento es de investigación.
