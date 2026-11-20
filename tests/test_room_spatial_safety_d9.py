"""D9: security regression for the authentic D5 spatial compositor.

The CAD fixtures are the original D4 bytes. These cases exercise the actual
D5 composition API without replacing its collision/geometric implementation.
A fake Maestro/CADExchange *producer* is used only in the public-boundary tests.
"""
from __future__ import annotations
import copy
import json
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from carpinova_agent import room_spatial as s

FIXTURES = Path(__file__).parent / 'fixtures' / 'room_spatial'

def cad(kind='BAJO'):
    return json.loads((FIXTURES / (kind+'_cad-exchange.json')).read_text(encoding='utf-8'))

def payload(model, kind='BAJO'):
    model['geometry_sha256'] = s._hash({key:value for key,value in model.items() if key!='geometry_sha256'})
    return [{'group_id':kind,'exchange':model,'origin_xyz_mm':[0,0,0],'rotation_deg':0}]

class D9SpatialSecurityRegression(TestCase):
    def test_optional_purchase_permission_true_fails_closed(self):
        source=cad();source['purchase_ready']=True
        with self.assertRaisesRegex(ValueError, 'certificación nominal'):
            s.compose_verified_exchanges(payload(source))

    def test_optional_f7c_permission_true_fails_closed(self):
        source=cad();source['can_generate_f7c']=True
        with self.assertRaisesRegex(ValueError, 'certificación nominal'):
            s.compose_verified_exchanges(payload(source))

    def test_optional_permission_null_fails_closed(self):
        for permission in ('purchase_ready','can_generate_f7c'):
            with self.subTest(permission=permission):
                source=cad();source[permission]=None
                with self.assertRaisesRegex(ValueError, 'certificación nominal'):
                    s.compose_verified_exchanges(payload(source))

    def test_optional_permission_false_preserves_nominal_review(self):
        source=cad();source['purchase_ready']=False;source['can_generate_f7c']=False
        result=s.compose_verified_exchanges(payload(source))
        self.assertEqual(result['piece_count'],29)
        self.assertEqual(result['status'],'REVIEW_ONLY')
        self.assertTrue(all(result[permission] is False for permission in s.PHYSICAL_FLAGS))

    def test_old_required_flags_remain_false(self):
        for permission in ('fabrication_ready','cutting_ready','drilling_ready'):
            with self.subTest(permission=permission):
                source=cad();source[permission]=True
                with self.assertRaises(ValueError):s.compose_verified_exchanges(payload(source))

    def test_not_a_trust_boundary_with_raw_client_exchange(self):
        raw=cad()
        a=payload(raw)
        a[0]['exchange']['boxes'][0]['size_xyz_mm'][0] += 1
        with self.assertRaisesRegex(ValueError,'integridad'):
            s.compose_verified_exchanges(a)

    def test_public_boundary_requires_server_produced_geometry(self):
        from carpinova_agent import maestro,cad_exchange
        seen=[]
        flags=dict(fabrication_ready=False,cutting_ready=False,drilling_ready=False,purchase_ready=False)
        def fake_maestro(request):
            seen.append(copy.deepcopy(request))
            return {'status':'DRAFT_NOT_FOR_CUTTING','modular':{'status':'DRAFT_NOT_FOR_CUTTING',
                    'fixture':request['module_spec']['fixture'],**flags},**flags}
        def fake_cad(model):return cad(model['fixture'])
        def fake_validate(e):
            if e['geometry_sha256'] != s._hash({k:v for k,v in e.items() if k!='geometry_sha256'}):
                raise ValueError('CAD digest mismatch')
            return e
        request={'review_kind':'room_layout_v1','assemblies':[
           {'group_id':'BAJO','module_spec':{'fixture':'BAJO'},'origin_xyz_mm':[0,0,0],'rotation_deg':0},
           {'group_id':'TORRE','module_spec':{'fixture':'TORRE'},'origin_xyz_mm':[1100,0,0],'rotation_deg':90},
        ],'service_zones':[]}
        with (patch.object(maestro,'consult_maestro',fake_maestro),
              patch.object(cad_exchange,'cad_exchange',fake_cad),
              patch.object(cad_exchange,'validate_exchange',fake_validate)):
            result=s.review_room_from_specs(request)
            self.assertEqual(result['piece_count'],36)
            self.assertEqual(len(seen),2)
            self.assertTrue(all(r['action']=='modular' for r in seen))
            tampered=copy.deepcopy(request)
            tampered['assemblies'][0]['exchange']=cad('BAJO')
            with self.assertRaises(ValueError):s.review_room_from_specs(tampered)

    def test_public_boundary_blocks_model_purchase_permission(self):
        from carpinova_agent import maestro,cad_exchange
        def forbidden_model(request):
            return {'status':'DRAFT_NOT_FOR_CUTTING','modular':{
                 'status':'DRAFT_NOT_FOR_CUTTING','fabrication_ready':False,
                 'cutting_ready':False,'drilling_ready':False,'purchase_ready':True},
                 'fabrication_ready':False,'cutting_ready':False,
                 'drilling_ready':False,'purchase_ready':True}
        request={'review_kind':'room_layout_v1','assemblies':[
            {'group_id':'BAJO','module_spec':{},'origin_xyz_mm':[0,0,0],'rotation_deg':0}],
            'service_zones':[]}
        with (patch.object(maestro,'consult_maestro',forbidden_model),
              patch.object(cad_exchange,'cad_exchange',side_effect=AssertionError('must not call CAD'))):
            with self.assertRaisesRegex(ValueError,'modelo nominal seguro'):
                s.review_room_from_specs(request)

    def test_collision_and_service_zone_block_permissions(self):
        a=payload(cad('BAJO'))
        a.append({'group_id':'TORRE','exchange':cad('TORRE'), 'origin_xyz_mm':[500,0,0], 'rotation_deg':0})
        result=s.compose_verified_exchanges(a, [
           {'zone_id':'PIPE','purpose':'plumbing','origin_xyz_mm':[1,100,30],'size_xyz_mm':[30,40,40]}])
        self.assertEqual(result['status'],'INTERFERENCE_REVIEW_REQUIRED')
        self.assertTrue(result['envelope_collisions'])
        self.assertEqual(result['service_zones'][0]['status'],'PANEL_INTERFERENCE')
        for permission in s.PHYSICAL_FLAGS:self.assertIs(result[permission],False)

    def test_valid_original_42_piece_layout_unchanged(self):
        a=[{'group_id':'BAJO','exchange':cad('BAJO'),'origin_xyz_mm':[0,0,0],'rotation_deg':0},
           {'group_id':'ALTO','exchange':cad('ALTO'),'origin_xyz_mm':[0,1420,0],'rotation_deg':0},
           {'group_id':'TORRE','exchange':cad('TORRE'),'origin_xyz_mm':[1100,0,0],'rotation_deg':90}]
        result=s.compose_verified_exchanges(a)
        self.assertEqual(result['piece_count'],42)
        self.assertEqual(result['status'],'REVIEW_ONLY')
        self.assertEqual(len(set(result['global_piece_ids'])),42)
