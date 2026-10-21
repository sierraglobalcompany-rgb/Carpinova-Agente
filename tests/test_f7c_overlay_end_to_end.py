"""Real repo integration regression: 50x50x80, 3 small drawers + one large.

Run only after the three audited source changes on the PR16 clone.
This imports the real F1/F6/F7C/Maestro/CADExchange/CSV/SVG modules; no stubs.
Illustrative dimensions require user approval and never authorize production.
"""
import copy
import json
from pathlib import Path
import unittest

from carpinova_agent.core import DesignError
from carpinova_agent.modular import design_modular_run
from carpinova_agent.cad_exchange import cad_exchange, validate_exchange
from carpinova_agent.modular_outputs import modular_bom_csv, modular_front_svg
from carpinova_agent.maestro import consult_maestro

FIXTURES = Path(__file__).resolve().parent.parent/'examples'


def load(style):
    path=FIXTURES/f'four-drawer-500x500x800-{style.upper()}-UNCONFIRMED.json'
    return json.loads(path.read_text(encoding='utf-8'))


class FourDrawerFullStackTests(unittest.TestCase):
    def _verify(self, style):
        request=load(style)
        answer=consult_maestro(request)
        model=design_modular_run(request['module_spec'])
        self.assertEqual(answer['status'],'DRAFT_NOT_FOR_CUTTING')
        self.assertEqual(model['piece_count'],28)
        self.assertEqual(len({p['piece_id'] for p in model['parts']}),28)
        self.assertEqual(model['dimensions_mm'],{'width':500,'height':800,'depth':500})
        self.assertEqual(len(model['modules'][0]['drawer_ids']),4)
        self.assertEqual([d['opening_height_mm'] for d in request['module_spec']['modules'][0]['drawers']],
                         [145,145,145,245])
        for flag in ('fabrication_ready','cutting_ready','drilling_ready','purchase_ready'):
            self.assertIs(model[flag],False)
        fronts=[p for p in model['parts'] if p['role']=='drawer_facade']
        self.assertEqual(len(fronts),4)
        self.assertEqual([f['source_engine'] for f in fronts],
                         ['F7C_EXPLICIT_'+style.upper()+'_FACADE']*4)
        self.assertTrue(all(f['opening_system']=='pending' for f in fronts))
        if style=='overlay':
            self.assertEqual(fronts[0]['nominal_origin_xyz_mm'],[2,8,-18])
            self.assertEqual([fronts[0]['nominal_face_x_mm'],fronts[0]['nominal_face_y_mm']],[496,165])
            self.assertEqual(fronts[-1]['nominal_face_y_mm'],265)
        else:
            self.assertEqual(fronts[0]['nominal_origin_xyz_mm'],[21,21,0])
            self.assertEqual(fronts[0]['nominal_face_x_mm'],458)
        exchange=cad_exchange(model)
        validate_exchange(exchange)
        if style=='overlay':
            self.assertEqual(exchange['front_shift_mm'],18)
            self.assertEqual(exchange['bounds_xyz_mm'],[500,800,518])
        else:
            self.assertNotIn('front_shift_mm',exchange)
            self.assertEqual(exchange['bounds_xyz_mm'],[500,800,500])
        self.assertEqual(len(exchange['boxes']),28)
        self.assertEqual({p['piece_id'] for p in model['parts']},
                         {box['piece_id'] for box in exchange['boxes']})
        csv_text=modular_bom_csv(model)
        svg_text=modular_front_svg(model)
        self.assertIn('M1-D4-DRAWER_FACADE',csv_text)
        self.assertIn('<svg',svg_text)
        self.assertIn('M1-D4-DRAWER_FACADE',svg_text)

    def test_inset_four_drawers_complete_contract(self):
        self._verify('inset')

    def test_overlay_four_drawers_complete_contract(self):
        self._verify('overlay')

    def test_overlay_collisions_rejected(self):
        request=load('overlay')['module_spec']
        drawers=request['modules'][0]['drawers']
        # Applets nominally have an 8 mm space; 18 mm overlap clashes.
        for index in (0,1):
            drawers[index]['facade']['top_overlap_mm']=18
            drawers[index+1]['facade']['bottom_overlap_mm']=18
        with self.assertRaises(DesignError):design_modular_run(request)

    def test_overlay_beyond_panel_thickness_rejected(self):
        req=load('overlay')['module_spec']
        req['modules'][0]['drawers'][0]['facade']['left_overlap_mm']=20
        with self.assertRaises(DesignError):design_modular_run(req)

    def test_handle_intent_does_not_enable_manufacturing(self):
        req=load('overlay')['module_spec']
        req['modules'][0]['drawers'][0]['facade']['opening_system']='handle'
        model=design_modular_run(req)
        self.assertIs(model['drilling_ready'],False)
        self.assertIs(model['fabrication_ready'],False)
        self.assertEqual(next(p for p in model['parts'] if p['piece_id']=='M1-D1-DRAWER_FACADE')['opening_system'],'handle')
        self.assertTrue(any('ficha/compatibilidad' in s for s in model['blockers']))


if __name__=='__main__':unittest.main()