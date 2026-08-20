"""Tests de la poda que evita la explosión de estados (design.md, "Evidencia
empírica"): olvido de objetos muertos en el suelo (prune_dead_ground) y la
macro-acción SWAP (DROP+PICKUP fusionados). Sin esto, UCS no termina en
tiempo razonable sobre un escenario con puertas+llaves reales — ver
CONTRATO.md §6, "DROP es el cuello de botella habitual".

Ejecutar desde backend/:  python -m pytest tests/test_pruning.py -v
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from simulator import ScenarioIndex, get_successors, prune_dead_ground, simulate
from demo_plan import build_plan, uniform_cost_search


def _scenario_con_puerta_y_carga_llena(**overrides):
    scenario = {
        "meta": {"description": "puerta + capacidad justa para forzar SWAP"},
        "robot": {"start": "A", "battery_start": 50, "battery_max": 50, "cargo_capacity": 1},
        "action_costs": {"pickup": 1, "drop": 1, "interact": 2, "recharge": 3},
        "corridors": [
            {"from": "A", "to": "B", "cost": 2, "door": "DOOR1"},
            {"from": "B", "to": "A", "cost": 2, "door": "DOOR1"},
        ],
        "doors": [{"id": "DOOR1", "state": "CLOSED", "between": ["A", "B"], "key": "KEY1"}],
        "keys": [{"id": "KEY1", "color": "cyan", "zone": "A", "weight": 1}],
        "tools": [{"id": "MULTITOOL", "repairs": "PANEL_A", "zone": "A", "weight": 1}],
        "materials": [],
        "panels": [
            {"id": "PANEL_A", "zone": "B", "state": "DAMAGED", "requires": {"tool": "MULTITOOL", "material": "NONE"}}
        ],
        "stations": [
            {"id": "STATION1", "zone": "B", "state": "OFFLINE", "requires": {"panels_ok": [], "stations_online": []}}
        ],
        "chargers": [],
        "goal": {"stations_online": ["STATION1"]},
    }
    scenario.update(overrides)
    return scenario


class TestPruneDeadGround(unittest.TestCase):
    """Una llave cuya puerta ya está OPEN no puede habilitar ninguna acción
    futura: su posición en el suelo debe desaparecer del estado, sin importar
    en qué zona haya quedado."""

    def test_llave_de_puerta_abierta_desaparece_del_suelo(self):
        scenario = _scenario_con_puerta_y_carga_llena(
            doors=[{"id": "DOOR1", "state": "OPEN", "between": ["A", "B"], "key": "KEY1"}],
        )
        idx = ScenarioIndex(scenario)
        state = idx.initial_state()
        # KEY1 sigue en el escenario crudo, pero la puerta ya está abierta:
        # initial_state() debe podarla de inmediato.
        self.assertNotIn("KEY1", dict(state.ground_keys))

    def test_dos_zonas_de_caida_distintas_para_un_objeto_muerto_son_el_mismo_estado(self):
        base = _scenario_con_puerta_y_carga_llena(
            doors=[{"id": "DOOR1", "state": "OPEN", "between": ["A", "B"], "key": "KEY1"}],
        )
        idx = ScenarioIndex(base)
        from simulator import State

        common = dict(
            battery=10, payload_keys=(), payload_tools=(), payload_materials=(),
            doors=(("DOOR1", "OPEN"),), panels=(("PANEL_A", "DAMAGED"),), stations=(("STATION1", "OFFLINE"),),
            ground_tools=(), ground_materials=(),
        )
        s_en_a = State(zone="A", ground_keys=(("KEY1", "A"),), **common)
        s_en_b = State(zone="B", ground_keys=(("KEY1", "B"),), **common)
        pruned_a = prune_dead_ground(idx, s_en_a)
        pruned_b = prune_dead_ground(idx, s_en_b)
        # Misma zona del robot en ambos (sólo cambiaba dónde cayó la llave
        # muerta) -> tras podar deben quedar idénticos.
        self.assertEqual(pruned_a.ground_keys, pruned_b.ground_keys)
        self.assertEqual(pruned_a.ground_keys, ())


class TestSwap(unittest.TestCase):
    """Con capacidad justa, soltar un ítem para recoger otro debe salir como
    un único sucesor SWAP (no dos nodos de búsqueda separados)."""

    def test_swap_se_genera_cuando_la_carga_esta_llena(self):
        scenario = _scenario_con_puerta_y_carga_llena()
        idx = ScenarioIndex(scenario)
        state = idx.initial_state()
        # Recoger KEY1 llena la capacidad (cargo_capacity=1).
        pk = [s for a, s in get_successors(idx, state) if a.kind == "PICKUP"][0]
        successors = get_successors(idx, pk)
        swaps = [a for a, _ in successors if a.kind == "SWAP"]
        self.assertTrue(swaps, "debería ofrecerse SWAP con la capacidad llena")
        self.assertEqual(swaps[0].step["_swap"][0]["op"], "DROP")
        self.assertEqual(swaps[0].step["_swap"][1]["op"], "PICKUP")

    def test_swap_se_traduce_a_drop_y_pickup_reales_y_pasa_el_simulador(self):
        scenario = _scenario_con_puerta_y_carga_llena()
        result = build_plan(scenario_raw=scenario)
        self.assertTrue(result["solution_found"])
        ops = [s["op"] for s in result["steps"]]
        self.assertNotIn("SWAP", ops)  # SWAP nunca llega al contrato
        self.assertTrue(set(ops) <= {"MOVE", "PICKUP", "DROP", "INTERACT"})
        final_state = simulate(scenario, result["steps"])
        self.assertEqual(final_state["stations"]["STATION1"], "ONLINE")
        self.assertEqual(sum(s["cost"] for s in result["steps"]), result["total_cost"])


if __name__ == "__main__":
    unittest.main()
