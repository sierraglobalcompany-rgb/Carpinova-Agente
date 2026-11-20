"""D8 room fit regression: measured room + no-go obstacle volumes.

D8 focal tests use original D4 CAD boxes and D5's REAL collision composer.
A separate public Maestro/F6/CADExchange smoke test uses the committed D5
example and NO mocked geometry boundary; it is run in the full repository.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch
from xml.etree import ElementTree as ET

from carpinova_agent.mcp_bridge import carpinova_consultar
from carpinova_agent import room_spatial as spatial

FIXTURES = Path(__file__).resolve().parent / 'fixtures' / 'room_spatial'
EXAMPLE = Path(__file__).resolve().parents[1] / 'examples' / 'room-layout-L-concept.json'


def a(group_id, position, rotation=0):
    return {'group_id': group_id,
            'module_spec': {'type': 'modular_run', 'fixture_for_test': group_id},
            'origin_xyz_mm': position, 'rotation_deg': rotation}


def fixture_boundary(request):
    if set(request) != {'review_kind', 'assemblies', 'service_zones'}:
        raise ValueError('Bad public D5 schema')
    assemblies = []
    for raw in request['assemblies']:
        if set(raw) != {'group_id', 'module_spec', 'origin_xyz_mm', 'rotation_deg'}:
            raise ValueError('untrusted geometry')
        gid = raw['group_id']
        if raw['module_spec'] != {'type': 'modular_run', 'fixture_for_test': gid}:
            raise ValueError('fixture mismatch')
        exchange = json.loads((FIXTURES / (gid + '_cad-exchange.json')).read_text('utf-8'))
        assemblies.append({'group_id': gid, 'exchange': exchange,
                           'origin_xyz_mm': raw['origin_xyz_mm'],
                           'rotation_deg': raw['rotation_deg']})
    return spatial.compose_verified_exchanges(assemblies, request['service_zones'])


def request(assemblies=None, room=None, zones=None):
    return {'review_kind': 'room_fit_v1',
            'assemblies': assemblies if assemblies is not None else [
                a('BAJO', [0, 0, 0]), a('TORRE', [1100, 0, 0])],
            'service_zones': zones if zones is not None else [],
            'room': room if room is not None else {
                'size_xyz_mm': [2000, 2500, 1500], 'obstacles': []}}


def obstacle(oid, origin, size=(20,20,20), kind='column'):
    return {'obstacle_id': oid, 'kind': kind,
            'origin_xyz_mm': list(origin), 'size_xyz_mm': list(size)}


def call(value):
    return carpinova_consultar(json.dumps(value, ensure_ascii=False))


class D8MeasuredRoomFit(TestCase):
    def setUp(self):
        stub = patch.object(spatial, 'review_room_from_specs', fixture_boundary)
        stub.start()
        self.addCleanup(stub.stop)

    def test_measured_empty_room_passes_nominal_and_preserves_flags(self):
        result = call(request())
        self.assertEqual(result['status'], 'ROOM_FIT_NOMINAL_ONLY')
        self.assertEqual(len(result['groups']), 2)
        self.assertTrue(all(g['inside_room'] for g in result['groups']))
        for flag in spatial.PHYSICAL_FLAGS:
            self.assertIs(result[flag], False)
        self.assertIn('NOT_A_STRUCTURAL', ' '.join(result['warnings']))

    def test_touching_room_boundary_is_not_a_penetration(self):
        r = request(assemblies=[a('BAJO',[0,0,0])], room={
            'size_xyz_mm': [1000, 800, 518], 'obstacles': []})
        self.assertEqual(call(r)['status'], 'ROOM_FIT_NOMINAL_ONLY')

    def test_outside_x_y_z_is_blocked_without_truncation(self):
        dims = ([999,800,518], [1000,799,518], [1000,800,517])
        for room_size in dims:
            with self.subTest(room_size=room_size):
                r = request(assemblies=[a('BAJO',[0,0,0])], room={
                    'size_xyz_mm': list(room_size), 'obstacles': []})
                result = call(r)
                self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
                self.assertFalse(result['groups'][0]['inside_room'])

    def test_obstacle_crosses_panel_and_blocks(self):
        r = request(room={'size_xyz_mm': [2000,2500,1500],
                          'obstacles': [obstacle('COL1',[1,100,30],(30,40,40))]})
        result = call(r)
        self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
        self.assertTrue(result['obstacle_piece_interferences'])
        self.assertTrue(result['obstacle_envelope_interferences'])

    def test_cavity_does_not_silently_waive_obstacle(self):
        r = request(assemblies=[a('BAJO',[0,0,0])], room={
            'size_xyz_mm':[1500,1500,1500],
            'obstacles':[obstacle('INVOID',[100,100,100],(20,20,20))]})
        result = call(r)
        self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
        self.assertTrue(result['obstacle_envelope_interferences'])
        self.assertEqual(result['obstacle_piece_interferences'], [])

    def test_obstacle_outside_room_fails_closed(self):
        r = request(room={'size_xyz_mm':[2000,2500,1500],
                          'obstacles':[obstacle('E1',[1990,100,100],(20,20,20))]})
        with self.assertRaisesRegex(ValueError,'fuera del recinto'):
            call(r)

    def test_clear_obstacle_does_not_block(self):
        r = request(room={'size_xyz_mm':[2000,2500,1500],
                          'obstacles':[obstacle('C1',[1050,0,1000]) ]})
        result = call(r)
        self.assertEqual(result['status'], 'ROOM_FIT_NOMINAL_ONLY')
        self.assertFalse(result['obstacle_envelope_interferences'])

    def test_determinism_independent_obstacle_order(self):
        o1 = obstacle('C1',[1050,0,1000])
        o2 = obstacle('C2',[1800,0,1000])
        r = request(room={'size_xyz_mm':[2000,2500,1500], 'obstacles':[o1,o2]})
        reversed_request = copy.deepcopy(r)
        reversed_request['room']['obstacles'].reverse()
        self.assertEqual(call(r)['room_fit_sha256'], call(reversed_request)['room_fit_sha256'])
        self.assertNotEqual(call(r)['room_fit_sha256'], call(request())['room_fit_sha256'])

    def test_strict_schema_and_no_fake_clearance(self):
        base = request()
        cases = [
            {'size_xyz_mm':[2000,2500,1500], 'obstacles': [], 'clearance_mm': 0},
            {'size_xyz_mm':[True,2500,1500], 'obstacles': []},
            {'size_xyz_mm':[2000,0,1500], 'obstacles': []},
            {'size_xyz_mm':[2000,2500,1500], 'obstacles':[obstacle('X',[0,0,0]),obstacle('X',[10,0,0])]},
            {'size_xyz_mm':[2000,2500,1500], 'obstacles':[obstacle('bad<svg>',[0,0,0])]},
            {'size_xyz_mm':[2000,2500,1500], 'obstacles':[obstacle('X',[0,0,0],kind='unsafe_cutout')]},
            {'size_xyz_mm':[2000,2500,1500], 'obstacles':[dict(obstacle('X',[0,0,0]), extra=1)]},
        ]
        for room in cases:
            with self.subTest(room=room), self.assertRaises(ValueError):
                r=copy.deepcopy(base);r['room']=room;call(r)

    def test_base_D5_layout_interference_is_not_hidden(self):
        r=request(assemblies=[a('BAJO',[0,0,0]),a('TORRE',[200,0,0])])
        result=call(r)
        self.assertEqual(result['layout_status'], 'INTERFERENCE_REVIEW_REQUIRED')
        self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
        self.assertTrue(result['layout_envelope_collisions'])

    def test_stated_access_zone_is_not_a_real_door_swing(self):
        r=request(room={'size_xyz_mm':[2000,2500,1500],
                        'obstacles':[obstacle('ACCESS1',[1050,0,1000],kind='opening_keepout')]})
        output=call(r)
        self.assertIn('OPENING_KEEP_OUT_IS_A_RECTANGLE', ' '.join(output['warnings']))
        self.assertEqual(output['status'], 'ROOM_FIT_NOMINAL_ONLY')

    def test_svg_is_parseable_and_uses_measured_dimensions(self):
        result=call(request())
        svg=ET.fromstring(result['top_view_svg'])
        self.assertEqual(svg.attrib['viewBox'], '0 0 2000 1500')
        self.assertIn('no fabricable', result['top_view_svg'])

    def test_rejects_client_injected_exchange(self):
        r=request();r['assemblies'][0]['exchange']={'geometry_sha256':'fake'}
        with self.assertRaises(ValueError):call(r)

    def test_flags_unlocked_by_untrusted_producer_rejected(self):
        def malicious(_):
            sample=request()
            x=fixture_boundary({'review_kind':'room_layout_v1',
                                'assemblies':sample['assemblies'],
                                'service_zones':sample['service_zones']})
            x['fabrication_ready']=True
            return x
        with patch.object(spatial,'review_room_from_specs',malicious):
            with self.assertRaisesRegex(ValueError,'permisos físicos'):
                call(request())

    def test_reservation_outside_room_is_not_nominal_approval(self):
        for zone_origin, size in [
            ([1900, 100, 1400], [200, 100, 200]),
            ([1500, 2450, 100], [20, 100, 20]),
            ([1500, 100, 1490], [20, 20, 50]),
        ]:
            with self.subTest(zone_origin=zone_origin):
                r = request(zones=[{'zone_id': 'SERVICE', 'purpose': 'plumbing',
                    'origin_xyz_mm': zone_origin, 'size_xyz_mm': size}])
                result = call(r)
                self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
                self.assertFalse(result['service_zone_room_fit'][0]['inside_room'])
                self.assertTrue(all(g['inside_room'] for g in result['groups']))
                self.assertTrue(all(result[f] is False for f in spatial.PHYSICAL_FLAGS))

    def test_reservation_touching_room_boundary_is_valid_for_room_fit(self):
        r = request(zones=[{'zone_id': 'SERVICE', 'purpose': 'electric',
            'origin_xyz_mm': [1970, 2470, 1470],
            'size_xyz_mm': [30, 30, 30]}])
        result = call(r)
        self.assertEqual(result['status'], 'ROOM_FIT_NOMINAL_ONLY')
        self.assertTrue(result['service_zone_room_fit'][0]['inside_room'])

    def test_obstacle_intersecting_service_zone_blocks_even_without_cabinet(self):
        room = {'size_xyz_mm': [2000, 2500, 1500],
                'obstacles': [obstacle('COLUMN', [1050, 100, 1000], (20, 20, 20))]}
        r = request(room=room, zones=[{'zone_id': 'PIPE', 'purpose': 'plumbing',
            'origin_xyz_mm': [1050, 100, 1000], 'size_xyz_mm': [20, 20, 20]}])
        result = call(r)
        self.assertEqual(result['status'], 'ROOM_FIT_REVIEW_REQUIRED')
        self.assertEqual(result['obstacle_envelope_interferences'], [])
        self.assertEqual(result['service_zone_obstacle_interferences'][0]['zone_id'], 'PIPE')
        self.assertEqual(result['service_zone_obstacle_interferences'][0]['obstacle_id'], 'COLUMN')
        self.assertEqual(result['service_zone_room_fit'][0]['inside_room'], True)
        self.assertTrue(all(result[f] is False for f in spatial.PHYSICAL_FLAGS))

    def test_svg_shows_service_reservations_in_measured_top_view(self):
        r = request(zones=[{'zone_id': 'SERVICE', 'purpose': 'plumbing',
            'origin_xyz_mm': [1800, 100, 1000], 'size_xyz_mm': [25, 25, 25]}])
        result = call(r)
        svg = ET.fromstring(result['top_view_svg'])
        service_rects = [rect for rect in svg.findall('{http://www.w3.org/2000/svg}rect')
                         if rect.attrib.get('stroke') == '#7c3aed']
        self.assertEqual(len(service_rects), 1)
        self.assertEqual(service_rects[0].attrib['x'], '1800')
        self.assertEqual(service_rects[0].attrib['y'], '1000')

    def test_geometry_digest_changes_when_room_changes(self):
        r=request()
        r2=copy.deepcopy(r)
        r2['room']['size_xyz_mm'][0]=2010
        self.assertEqual(call(r)['layout_sha256'],call(r2)['layout_sha256'])
        self.assertNotEqual(call(r)['room_fit_sha256'],call(r2)['room_fit_sha256'])


class D8RealMaestroAndCadExchangeSmoke(TestCase):
    def test_real_public_maestro_cad_two_kitchen_modules(self):
        # No patches: exact D5 example -> Maestro -> F6 -> CADExchange -> D8.
        original=json.loads(EXAMPLE.read_text('utf-8'))
        original['review_kind']='room_fit_v1'
        original['room']={'size_xyz_mm':[2000,2500,2000], 'obstacles':[]}
        result=call(original)
        self.assertEqual(result['status'],'ROOM_FIT_NOMINAL_ONLY')
        self.assertEqual(len(result['groups']),2)
        self.assertTrue(all(g['inside_room'] for g in result['groups']))
        for flag in spatial.PHYSICAL_FLAGS:self.assertIs(result[flag],False)
