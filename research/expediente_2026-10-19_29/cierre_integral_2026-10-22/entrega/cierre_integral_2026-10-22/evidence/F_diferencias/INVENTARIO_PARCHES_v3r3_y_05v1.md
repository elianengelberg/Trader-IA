# Inventario de diferencias (generado; la revisión de cada hallazgo está en REVISION_DIFERENCIAS.md)

## 01_obligatorio_D1_D3_motor_y_pruebas_definitivas.patch

| Archivo | Fragmentos | + | − | Nuevo |
|---|---|---|---|---|
| `packages/tia/src/tia/backtest/engine.py` | 7 | 67 | 8 | no |
| `packages/tia/src/tia/execution/paper.py` | 1 | 9 | 0 | no |
| `tests/unit/test_backtest_order_hygiene.py` | 1 | 342 | 0 | sí |

Archivos: 3 · líneas +418 / −8

Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):

- ninguna

## 02v3_obligatorio_trazabilidad_version_motor_CORREGIDO.patch

| Archivo | Fragmentos | + | − | Nuevo |
|---|---|---|---|---|
| `docs/ARCHITECTURE.md` | 1 | 10 | 0 | no |
| `packages/tia/src/tia/api/state.py` | 1 | 2 | 0 | no |
| `packages/tia/src/tia/backtest/engine.py` | 4 | 76 | 2 | no |
| `packages/tia/src/tia/backtest/result.py` | 1 | 7 | 0 | no |
| `packages/tia/src/tia/persistence/repositories.py` | 2 | 55 | 0 | no |
| `tests/integration/test_backtest_provenance.py` | 1 | 302 | 0 | sí |

Archivos: 6 · líneas +452 / −2

Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):

- `tests/integration/test_backtest_provenance.py` · red o servicios externos: `import httpx`
- `tests/integration/test_backtest_provenance.py` · red o servicios externos: `from tia.api.app import create_app`
- `tests/integration/test_backtest_provenance.py` · credenciales: `monkeypatch.setenv("TIA_DEMO_PASSWORD", "provenance-password-not-a-secret")`
- `tests/integration/test_backtest_provenance.py` · red o servicios externos: `update={"database_url": f"sqlite+aiosqlite:///{tmp_path / 'api.db'}"}`
- `tests/integration/test_backtest_provenance.py` · red o servicios externos: `transport = httpx.ASGITransport(app=app)`
- `tests/integration/test_backtest_provenance.py` · red o servicios externos: `async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:`
- `tests/integration/test_backtest_provenance.py` · credenciales: `json={"username": "provenance-operator", "password": "provenance-password-not-a-secret"},`

## 03_opcional_pruebas_reloj_y_persistencia.patch

| Archivo | Fragmentos | + | − | Nuevo |
|---|---|---|---|---|
| `tests/integration/test_account_restore.py` | 3 | 15 | 9 | no |
| `tests/integration/test_adverse_recovery.py` | 4 | 16 | 0 | no |
| `tests/integration/test_risk_state_persistence.py` | 3 | 14 | 4 | no |

Archivos: 3 · líneas +45 / −13

Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):

- ninguna

## 04_opcional_CI_versiones_fijadas.patch

| Archivo | Fragmentos | + | − | Nuevo |
|---|---|---|---|---|
| `.github/workflows/ci.yml` | 1 | 2 | 1 | no |
| `constraints/ci-py311.txt` | 1 | 80 | 0 | sí |

Archivos: 2 · líneas +82 / −1

Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):

- `constraints/ci-py311.txt` · red o servicios externos: `httpx2==2.16.0`
- `constraints/ci-py311.txt` · red o servicios externos: `httpx==0.28.1`
- `constraints/ci-py311.txt` · red o servicios externos: `types-requests==2.33.0.20261006`
- `constraints/ci-py311.txt` · red o servicios externos: `urllib3==2.8.0`
- `constraints/ci-py311.txt` · red o servicios externos: `websockets==17.3`

## 05_propuesta_guarda_version_motor.patch

| Archivo | Fragmentos | + | − | Nuevo |
|---|---|---|---|---|
| `tests/integration/test_engine_version_contract.py` | 1 | 504 | 0 | sí |

Archivos: 1 · líneas +504 / −0

Líneas agregadas que tocan un patrón de riesgo (para revisar a mano; un patrón no es un defecto):

- `tests/integration/test_engine_version_contract.py` · pruebas desactivadas: `pytest.skip(f"the engine records version {version}: it does not claim D1-D3")`

