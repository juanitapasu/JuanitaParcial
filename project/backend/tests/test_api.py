"""Prueba de integración de POST /api/solve contra el contrato HTTP real
(CONTRATO.md §2), no contra las funciones internas del agente.

Esto es justo lo que faltaba antes: los tests anteriores llamaban
uniform_cost_search()/get_successors() directamente, nunca pasaban por
FastAPI. Aquí se levanta la app con TestClient y se golpea /api/solve como
lo haría el frontend, verificando forma de respuesta, las 4 operaciones
válidas y el manejo de entrada malformada (sin traceback, con 400 claro).

Ejecutar desde backend/:  python -m pytest tests/test_api.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from fastapi.testclient import TestClient

from main import app

client = TestClient(app)

VALID_OPS = {"MOVE", "PICKUP", "DROP", "INTERACT"}
VALID_INTERACT_ACTIONS = {"OPEN_DOOR", "REPAIR", "ACTIVATE", "RECHARGE"}


def _small_scenario(**overrides):
    scenario = {
        "meta": {"description": "escenario chico para el contrato HTTP"},
        "robot": {"start": "A", "battery_start": 50, "battery_max": 50, "cargo_capacity": 2},
        "action_costs": {"pickup": 1, "drop": 1, "interact": 2, "recharge": 3},
        "corridors": [
            {"from": "A", "to": "B", "cost": 4},
            {"from": "B", "to": "A", "cost": 4},
        ],
        "doors": [],
        "keys": [],
        "tools": [],
        "materials": [],
        "panels": [],
        "stations": [
            {"id": "STATION1", "zone": "B", "state": "OFFLINE", "requires": {"panels_ok": [], "stations_online": []}}
        ],
        "chargers": [],
        "goal": {"stations_online": ["STATION1"]},
    }
    scenario.update(overrides)
    return scenario


class TestHealth(unittest.TestCase):
    def test_health_ok(self):
        resp = client.get("/api/health")
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json(), {"status": "ok"})


class TestContratoSolve(unittest.TestCase):
    """El JSON que sale de /api/solve debe cumplir CONTRATO.md §2 al pie de
    la letra: sólo 4 operaciones, INTERACT con action válido, forma exacta."""

    def test_forma_de_la_respuesta_y_operaciones_validas(self):
        resp = client.post("/api/solve", json={"scenario": _small_scenario()})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIn("solution_found", body)
        self.assertIn("total_cost", body)
        self.assertIn("steps", body)
        self.assertTrue(body["solution_found"])
        self.assertEqual(body["total_cost"], 4 + 2)  # MOVE + ACTIVATE

        for step in body["steps"]:
            self.assertIn(step["op"], VALID_OPS)
            if step["op"] == "INTERACT":
                self.assertIn(step["action"], VALID_INTERACT_ACTIONS)

        # Los costos declarados deben sumar exactamente total_cost (auditoría
        # de CONTRATO.md §5).
        self.assertEqual(sum(s["cost"] for s in body["steps"]), body["total_cost"])

    def test_scenario_path_alternativo_tambien_funciona(self):
        # No usamos el body vacío aquí a propósito: eso cargaría
        # scenarios/scenario.json (el escenario real de 5 zonas), cuya
        # búsqueda óptima tarda ~50s — demasiado para un test unitario.
        # Se prueba el mismo mecanismo de carga con un escenario chico propio.
        import json
        import tempfile

        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8") as f:
            json.dump(_small_scenario(), f)
            path = f.name
        try:
            resp = client.post("/api/solve", json={"scenario_path": path})
            self.assertEqual(resp.status_code, 200)
            body = resp.json()
            self.assertTrue(body["solution_found"])
        finally:
            Path(path).unlink(missing_ok=True)


class TestEntradaMalformada(unittest.TestCase):
    """Un escenario inválido debe responder 400 con el motivo, nunca un
    traceback de 500 ni colgarse."""

    def test_escenario_sin_robot_da_400(self):
        resp = client.post("/api/solve", json={"scenario": {"bogus": True}})
        self.assertEqual(resp.status_code, 400)
        self.assertIn("inválido", resp.json()["detail"])

    def test_json_invalido_da_422(self):
        resp = client.post(
            "/api/solve",
            content="esto no es json",
            headers={"Content-Type": "application/json"},
        )
        self.assertEqual(resp.status_code, 422)

    def test_escenario_sin_solucion_responde_failure_no_error(self):
        scenario = _small_scenario(
            stations=[
                {
                    "id": "STATION1",
                    "zone": "B",
                    "state": "OFFLINE",
                    "requires": {"panels_ok": ["PANEL_GHOST"], "stations_online": []},
                }
            ]
        )
        resp = client.post("/api/solve", json={"scenario": scenario})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertFalse(body["solution_found"])
        self.assertEqual(body["steps"], [])


if __name__ == "__main__":
    unittest.main()
