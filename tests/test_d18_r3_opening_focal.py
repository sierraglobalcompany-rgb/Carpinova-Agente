"""Focal renderer contract for D18 R3: nominal doors are presentation-only."""
from __future__ import annotations
import json
import re
import unittest
from pathlib import Path
from carpinova_agent.room_3d_review import render_room_3d_html

class D18R3OpeningFocal(unittest.TestCase):
    def test_scene_has_only_real_door_controls_and_no_new_geometry(self):
        group='BAJO_COCINA_2P'
        boxes=[
            {'group_id':group,'piece_id':group+':LEFT','role':'left_side',
             'origin_xyz_mm':[0,0,18],'size_xyz_mm':[18,720,560]},
            {'group_id':group,'piece_id':group+':TOP','role':'top',
             'origin_xyz_mm':[18,702,18],'size_xyz_mm':[864,18,560]},
            {'group_id':group,'piece_id':group+':SHELF','role':'shelf_horizontal',
             'origin_xyz_mm':[18,338,18],'size_xyz_mm':[864,18,500]},
            {'group_id':group,'piece_id':group+':FRONT_LEFT','role':'front_left',
             'origin_xyz_mm':[3,3,0],'size_xyz_mm':[445,714,18]},
            {'group_id':group,'piece_id':group+':FRONT_RIGHT','role':'front_right',
             'origin_xyz_mm':[452,3,0],'size_xyz_mm':[445,714,18]},
        ]
        review={
            'review_kind':'room_layout_v1','status':'REVIEW_ONLY',
            'groups':[{'group_id':group,'origin_xyz_mm':[0,0,0],
                       'bounds_xyz_mm':[900,720,578],'piece_count':len(boxes)}],
            'world_boxes':boxes,'piece_count':len(boxes),
            'service_zones':[],'warnings':['ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY'],
            'layout_sha256':'f'*64,
            'fabrication_ready':False,'cutting_ready':False,'drilling_ready':False,
            'purchase_ready':False,'can_generate_f7c':False,
        }
        original=json.dumps(review,sort_keys=True)
        html=render_room_3d_html(review)
        self.assertEqual(original,json.dumps(review,sort_keys=True))
        self.assertIn('Abrir puertas nominales',html)
        self.assertIn('const doorAngles=new Map()',html)
        self.assertIn('const hingeFaces=',html)
        self.assertIn('const paintLayer=',html)
        self.assertIn("if(role==='top')return 3",html)
        self.assertIn('Sin bisagras, holguras de giro ni cargas verificadas',html)
        self.assertIn('Esta escena contiene cajones nominales',html)
        self.assertIn('0–90°',html)
        self.assertIn('NO FABRICAR',html)
        self.assertNotRegex(html,r'(?i)<script\s+src=')
        match=re.search(r'<script id="scene-data" type="application/json">(.*?)</script>',html,re.S)
        self.assertIsNotNone(match)
        scene=json.loads(match.group(1))
        self.assertEqual(len(scene['boxes']),len(boxes))
        self.assertEqual([b['origin'] for b in scene['boxes']], [b['origin_xyz_mm'] for b in boxes])
        self.assertEqual([b['size'] for b in scene['boxes']], [b['size_xyz_mm'] for b in boxes])
        self.assertEqual([b['role'] for b in scene['boxes']], [b['role'] for b in boxes])
        self.assertEqual(scene['status'],'REVIEW_ONLY')

if __name__=='__main__':
    unittest.main()
