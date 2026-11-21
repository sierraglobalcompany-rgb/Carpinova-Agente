"""D18 NEW tests, no historical D12-D17 replay."""
from __future__ import annotations

import json
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from carpinova_agent.room_3d_review import RoomViewerError, main, render_room_3d_html


def room():
    return {
        'review_kind':'room_layout_v1','status':'REVIEW_ONLY',
        'fabrication_ready':False,'cutting_ready':False,
        'drilling_ready':False,'purchase_ready':False,'can_generate_f7c':False,
        'layout_sha256':'a'*64,
        'groups':[{'group_id':'BASE','origin_xyz_mm':[0,0,0],
                   'bounds_xyz_mm':[800,720,560],'piece_count':2}],
        'world_boxes':[
            {'group_id':'BASE','piece_id':'BASE:LEFT_SIDE','role':'left_side',
             'origin_xyz_mm':[0,0,0],'size_xyz_mm':[18,720,560]},
            {'group_id':'BASE','piece_id':'BASE:FRONT_RIGHT','role':'front_right',
             'origin_xyz_mm':[18,0,0],'size_xyz_mm':[380,700,18]}],
        'piece_count':2,'service_zones':[],
        'warnings':['ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY'],
    }


class Room3DViewerD18(unittest.TestCase):
    def test_offline_html_contains_only_verified_boxes_and_nominal_warning(self):
        source=room(); old=json.dumps(source,sort_keys=True)
        html=render_room_3d_html(source)
        self.assertIn('NO CORTAR NI FABRICAR',html)
        self.assertIn('BASE:FRONT_RIGHT',html)
        self.assertIn('left_side',html)
        self.assertNotIn('https://',html)
        self.assertNotIn('<script src=',html)
        self.assertEqual(old,json.dumps(source,sort_keys=True))
        self.assertEqual(html,render_room_3d_html(source))

    def test_permissions_are_fail_closed(self):
        for key,val in [('fabrication_ready',True),('purchase_ready',None),
                        ('can_generate_f7c',1),('cutting_ready',True)]:
            bad=room(); bad[key]=val
            with self.subTest(key=key),self.assertRaises(RoomViewerError):
                render_room_3d_html(bad)

    def test_untrusted_status_or_review_kind_rejected(self):
        for key,val in [('review_kind','CADExchange'),('status','GO'),
                        ('layout_sha256','xyz')]:
            bad=room();bad[key]=val
            with self.subTest(key=key),self.assertRaises(RoomViewerError):
                render_room_3d_html(bad)

    def test_tampered_world_box_and_duplicate_id_block(self):
        bad=room();bad['world_boxes'][0]['origin_xyz_mm']=[801,0,0]
        with self.assertRaises(RoomViewerError):render_room_3d_html(bad)
        bad=room();bad['world_boxes'][1]['piece_id']=bad['world_boxes'][0]['piece_id']
        with self.assertRaises(RoomViewerError):render_room_3d_html(bad)
        bad=room();bad['piece_count']=4
        with self.assertRaises(RoomViewerError):render_room_3d_html(bad)

    def test_rejects_boolean_float_negative_and_missing_coordinates(self):
        for value in ([True,720,560],[0,-1,560],[0,720],None,[0,0,30000]):
            bad=room();bad['groups'][0]['origin_xyz_mm']=value
            with self.subTest(value=value),self.assertRaises(RoomViewerError):
                render_room_3d_html(bad)

    def test_json_injection_cannot_close_script_tag(self):
        bad=room();bad['warnings']=['</script><img src=x onerror=alert(1)>']
        html=render_room_3d_html(bad)
        self.assertEqual(html.count('</script>'),2)
        self.assertNotIn('<img src=x',html)
        self.assertIn('\\u003c/script',html)

    def test_cli_rebuilds_public_maestro_and_never_overwrites(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d); i=p/'request.json';o=p/'scene.html'
            request={'review_kind':'room_layout_v1','assemblies':[],'service_zones':[]}
            i.write_text(json.dumps(request),encoding='utf-8')
            called=[]
            shim=types.ModuleType('carpinova_agent.room_spatial')
            def review(req):called.append(req);return room()
            shim.review_room_from_specs=review
            with patch.dict(sys.modules,{'carpinova_agent.room_spatial':shim}):
                self.assertEqual(main(['--input',str(i),'--output',str(o)]),0)
                self.assertEqual(called,[request]);self.assertIn('BASE:FRONT_RIGHT',o.read_text())
                with self.assertRaises(FileExistsError):
                    main(['--input',str(i),'--output',str(o)])
                self.assertEqual(called,[request,request])

    def test_cli_rejects_untrusted_client_cad_before_maestro(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d);i=p/'request.json'
            request={'review_kind':'room_layout_v1','assemblies':[],
                     'service_zones':[],'world_boxes':[{'role':'front'}]}
            i.write_text(json.dumps(request),encoding='utf-8')
            with self.assertRaises(SystemExit) as e:
                main(['--input',str(i),'--output',str(p/'scene.html')])
            self.assertEqual(e.exception.code,2)
            self.assertFalse((p/'scene.html').exists())

    def test_interference_is_not_disguised(self):
        bad=room();bad['status']='INTERFERENCE_REVIEW_REQUIRED';bad['warnings'].append('OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL')
        html=render_room_3d_html(bad)
        self.assertIn('INTERFERENCE_REVIEW_REQUIRED',html)
        self.assertIn('OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL',html)


if __name__=='__main__': unittest.main()
