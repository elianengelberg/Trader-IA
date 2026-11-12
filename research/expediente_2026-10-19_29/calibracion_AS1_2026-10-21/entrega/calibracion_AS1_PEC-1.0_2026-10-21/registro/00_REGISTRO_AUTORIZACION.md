# 00 — Registro de la autorización A-S1

- **Qué se autorizó:** A-S1, la calibración sintética de la prueba primaria (MEC v0.2 §5), tal como la describe
  `documentos_para_autorizar/AS1_CALIBRACION_Y_A8_DELTA.md` del paquete r1 (`a8056ced…`).
- **Texto literal del propietario**, en el chat de esta sesión, el 2026-10-21 (recibido antes de las 16:11 UTC):
  > autorizo A-S1, ejecutá la calibración
- **Referencia que se pasa a `--autorizacion`:**
  `A-S1: autorización del propietario en el chat de la sesión, 2026-10-21 («autorizo A-S1, ejecutá la calibración»). Transcripción, no firma.`

**Qué es y qué no es este registro:**
- Es una **transcripción**, no una firma. No se generó ni se simuló ninguna firma ni clave en nombre del propietario.
- Su autenticidad depende solo de este chat; no tiene una raíz independiente.
- Autoriza **solo** A-S1. No autoriza:
  - δ (A8 / D-S4);
  - la firma de T;
  - publicar commits;
  - leer datos de mercado;
  - nada de lo demás que figura en `06_AUTORIZACIONES_PENDIENTES.md`.
- La calibración usa **solo datos sintéticos**. No toca T, T-MULTI, el repositorio ni las entregas históricas.
