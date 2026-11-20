"""D12 regressions for canonical F6 -> CADExchange -> sheet-review roles.

Tests are prepared for Codex to execute on the integrated D4-D12 checkout.
No separate geometry engine, BOM builder or permission authority is introduced.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
import unittest
from unittest.mock import patch

from carpinova_agent.board_plan_review import (
    _CONCEPT_ROLES, _PHYSICAL_ROLES, _ROLE_PLANE,
    _validate_maestro_cad, build_board_plan_review,
)
from carpinova_agent.maestro import MaestroError
from carpinova_agent.mcp_bridge import carpinova_consultar


ROLES = {
    'divider_vertical': 'YZ',
    'shelf_horizontal': 'XZ',
    'countertop': 'XZ',
    'upper_front_tie': 'XY',
    'upper_rear_tie': 'XY',
    'lower_rear_tie': 'XY',
}
PHYSICAL_FLAGS = ('fabrication_ready', 'cutting_ready', 'drilling_ready', 'purchase_ready')
ROOT = Path(__file__).resolve().parents[1]


def pair(role: str, plane: str, identifier: str) -> tuple[dict, dict]:
    size = {
        'XY': [420, 320, 18],
        'XZ': [420, 18, 320],
        'YZ': [18, 320, 420],
    }[plane]
    part = {
        'piece_id': identifier, 'role': role,
        'module_id': 'M1', 'material_id': 'MELAMINA_18',
        'face_plane': plane, 'nominal_face_x_mm': 420,
        'nominal_face_y_mm': 320, 'thickness_mm': 18,
        'grain_axis': 'UNCONFIRMED',
        'edgebanding_edges': 'UNCONFIRMED',
        'edgebanding_thickness_mm': None,
    }
    box = {
        'piece_id': identifier, 'role': role, 'module_id': 'M1',
        'material_id': 'MELAMINA_18', 'size_xyz_mm': size,
        'grain_world_axis': 'UNCONFIRMED',
        'construction_geometry': 'NOMINAL_PANEL_BOX',
    }
    return part, box


class BoardPlanF6CanonicalRolesD12(unittest.TestCase):
    def test_all_six_canonical_f6_roles_are_board_review_physical(self):
        for role, plane in ROLES.items():
            with self.subTest(role=role):
                self.assertIn(role, _PHYSICAL_ROLES)
                self.assertEqual(_ROLE_PLANE[role], plane)
                part, box = pair(role, plane, f'M1-{role}')
                physical, concepts = _validate_maestro_cad(
                    {'parts': [part]}, {'boxes': [box]})
                self.assertEqual([p['piece_id'] for p in physical], [part['piece_id']])
                self.assertEqual(concepts, [])

    def test_combined_closet_shelf_divider_countertop_and_coffee_ties(self):
        pairs = [pair(role, plane, f'P{i}') for i, (role, plane)
                 in enumerate(ROLES.items(), 1)]
        physical, concepts = _validate_maestro_cad(
            {'parts': [item[0] for item in pairs]},
            {'boxes': [item[1] for item in pairs]},
        )
        self.assertEqual(len(physical), 6)
        self.assertEqual(concepts, [])

    def test_leg_concept_remains_excluded_from_board_count(self):
        self.assertIn('support_leg_concept', _CONCEPT_ROLES)
        self.assertNotIn('support_leg_concept', _PHYSICAL_ROLES)
        side = pair('left_side', 'YZ', 'SIDE')
        leg = pair('support_leg_concept', 'XY', 'LEG')
        physical, concepts = _validate_maestro_cad(
            {'parts': [side[0], leg[0]]},
            {'boxes': [side[1], leg[1]]},
        )
        self.assertEqual([p['piece_id'] for p in physical], ['SIDE'])
        self.assertEqual([p['piece_id'] for p in concepts], ['LEG'])

    def test_invalid_plane_cannot_be_reclassified_for_sheets(self):
        part, box = pair('divider_vertical', 'XY', 'BAD')
        with self.assertRaisesRegex(MaestroError, 'face_plane'):
            _validate_maestro_cad({'parts': [part]}, {'boxes': [box]})

    def test_mismatched_cad_size_still_rejected(self):
        part, box = pair('countertop', 'XZ', 'COUNTER')
        box['size_xyz_mm'][1] += 1
        with self.assertRaisesRegex(MaestroError, 'CADExchange no coincide'):
            _validate_maestro_cad({'parts': [part]}, {'boxes': [box]})


class BoardPlanSafetyD12(unittest.TestCase):
    def setUp(self):
        self.request = {
            'review_kind': 'board_plan_nominal',
            'source_request': {'action': 'modular', 'module_spec': {'type': 'modular_run'}},
        }
        self.good = {
            'status': 'DRAFT_NOT_FOR_CUTTING',
            'modular': {'status': 'DRAFT_NOT_FOR_CUTTING',
                        'can_generate_f7c': False, **{p: False for p in PHYSICAL_FLAGS}},
            **{p: False for p in PHYSICAL_FLAGS},
        }

    def assert_blocked_without_cad(self, data: dict):
        with patch('carpinova_agent.board_plan_review.consult_maestro', return_value=data), \
                patch('carpinova_agent.board_plan_review.cad_exchange',
                      side_effect=AssertionError('No CAD on unsafe state')) as cad:
            result = build_board_plan_review(self.request)
        self.assertEqual(result['status'], 'CONCEPT_ONLY')
        self.assertIsNone(result['estimated_nominal_sheet_count'])
        for flag in PHYSICAL_FLAGS:
            self.assertIs(result[flag], False)
        self.assertIs(result['can_generate_f7c'], False)
        cad.assert_not_called()

    def test_maestro_or_module_release_flag_blocks_before_cad(self):
        for where in ('maestro', 'modular'):
            for flag in PHYSICAL_FLAGS:
                with self.subTest(where=where, flag=flag):
                    data = copy.deepcopy(self.good)
                    target = data if where == 'maestro' else data['modular']
                    target[flag] = True
                    self.assert_blocked_without_cad(data)
                    target[flag] = None
                    self.assert_blocked_without_cad(data)

    def test_can_generate_f7c_true_or_null_blocks_before_cad(self):
        for where in ('maestro', 'modular'):
            for forbidden in (True, None):
                with self.subTest(where=where, value=forbidden):
                    data = copy.deepcopy(self.good)
                    target = data if where == 'maestro' else data['modular']
                    target['can_generate_f7c'] = forbidden
                    self.assert_blocked_without_cad(data)

    def test_maestro_bad_status_blocks_before_cad(self):
        data = copy.deepcopy(self.good)
        data['status'] = 'CONCEPT_ONLY'
        self.assert_blocked_without_cad(data)


class BoardPlanRealF6RoleD12(unittest.TestCase):
    def test_real_f6_shelf_reaches_board_plan_through_cad_exchange(self):
        spec = json.loads(
            (ROOT / 'examples' / 'modular-mixed-kitchen-b5.json').read_text(
                encoding='utf-8'))
        request = {
            'review_kind': 'board_plan_nominal',
            'source_request': {'action': 'modular', 'module_spec': spec},
        }
        result = carpinova_consultar(json.dumps(request, ensure_ascii=False))

        self.assertEqual(result['status'], 'NEEDS_MATERIAL_CONFIRMATION')
        self.assertIn('KITCHEN_LEFT-SHELF', result['piece_ids'])
        self.assertTrue(result['cad_part_source_match'])
        self.assertEqual(result['physical_piece_count'], len(result['piece_ids']))
        self.assertRegex(result['geometry_sha256'], r'^[0-9a-f]{64}$')
        self.assertIs(result['can_generate_f7c'], False)
        for flag in PHYSICAL_FLAGS:
            self.assertIs(result[flag], False, flag)


if __name__ == '__main__':
    unittest.main()
