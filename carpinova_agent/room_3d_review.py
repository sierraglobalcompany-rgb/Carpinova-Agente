"""D18: offline 3D nominal viewer of already verified room_layout_v1 CAD boxes.

The CLI accepts only the original module specifications and rebuilds the room
via Maestro/F6/CADExchange. It never accepts untrusted caller-provided boxes,
modifies parts, or grants cutting/fabrication authority.
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any

_FLAGS = ("fabrication_ready", "cutting_ready", "drilling_ready",
          "purchase_ready", "can_generate_f7c")
_SAFE_ID = re.compile(r"^[A-Za-z][A-Za-z0-9_:.-]{0,100}$")
_MAX_SIZE = 256_000


class RoomViewerError(ValueError):
    """Untrusted or incomplete nominal room cannot be shown as verified."""


def _vec(raw: Any, name: str, *, positive: bool = False) -> list[int]:
    if (type(raw) is not list or len(raw) != 3
            or any(type(v) is not int or v < (1 if positive else 0)
                   or v > 20000 for v in raw)):
        raise RoomViewerError(f"{name}: se necesitan 3 milímetros enteros válidos")
    return raw


def _record_id(value: Any, label: str) -> str:
    if type(value) is not str or not _SAFE_ID.fullmatch(value):
        raise RoomViewerError(f"{label}: identificador inválido")
    return value


def _payload(review: Any) -> dict[str, Any]:
    if (type(review) is not dict or review.get("review_kind") != "room_layout_v1"
            or review.get("status") not in {"REVIEW_ONLY", "INTERFERENCE_REVIEW_REQUIRED"}
            or any(review.get(flag) is not False for flag in _FLAGS)):
        raise RoomViewerError("La escena requiere room_layout_v1 con permisos físicos false")
    groups = review.get("groups")
    boxes = review.get("world_boxes")
    if (type(groups) is not list or not 1 <= len(groups) <= 6
            or type(boxes) is not list or not 1 <= len(boxes) <= 432
            or review.get("piece_count") != len(boxes)):
        raise RoomViewerError("Conjunto CAD incompleto o excedido")
    group_ids: set[str] = set()
    clean_groups = []
    group_bounds = {}
    for item in groups:
        if type(item) is not dict:
            raise RoomViewerError("Grupo inválido")
        gid = _record_id(item.get("group_id"), "group_id")
        if gid in group_ids:
            raise RoomViewerError("Grupos duplicados")
        group_ids.add(gid)
        origin = _vec(item.get("origin_xyz_mm"), "origen de grupo")
        size = _vec(item.get("bounds_xyz_mm"), "volumen de grupo", positive=True)
        if any(origin[i] + size[i] > 20000 for i in range(3)):
            raise RoomViewerError("Grupo fuera de límites")
        group_bounds[gid] = (origin, size)
        clean_groups.append({"id": gid, "origin": origin, "size": size})
    seen: set[str] = set()
    clean_boxes = []
    by_group = {gid: 0 for gid in group_ids}
    for item in boxes:
        if type(item) is not dict:
            raise RoomViewerError("Panel CAD inválido")
        gid = _record_id(item.get("group_id"), "group_id de panel")
        pid = _record_id(item.get("piece_id"), "piece_id")
        role = _record_id(item.get("role"), "rol")
        if gid not in group_ids or pid in seen:
            raise RoomViewerError("Panel sin grupo válido o identificador duplicado")
        seen.add(pid)
        origin = _vec(item.get("origin_xyz_mm"), "origen de panel")
        size = _vec(item.get("size_xyz_mm"), "volumen de panel", positive=True)
        base, bounds = group_bounds[gid]
        if any(origin[i] < base[i] or origin[i] + size[i] > base[i] + bounds[i]
               for i in range(3)):
            raise RoomViewerError("Panel CAD fuera de la envolvente verificada")
        by_group[gid] += 1
        clean_boxes.append({"id": pid, "group": gid, "role": role,
                            "origin": origin, "size": size})
    if any(item.get("piece_count") != by_group[item["group_id"]]
           for item in groups):
        # Existing room_layout_v1 includes group piece counts; refuse discrepancy.
        raise RoomViewerError("El conteo de paneles por grupo no corresponde")
    zones = review.get("service_zones")
    if type(zones) is not list or len(zones) > 12:
        raise RoomViewerError("Reservas de servicio inválidas")
    clean_zones = []
    for item in zones:
        if type(item) is not dict:
            raise RoomViewerError("Zona inválida")
        clean_zones.append({"id": _record_id(item.get("zone_id"), "zona"),
                            "origin": _vec(item.get("origin_xyz_mm"), "origen zona"),
                            "size": _vec(item.get("size_xyz_mm"), "tamaño zona", positive=True)})
    warnings = review.get("warnings")
    if type(warnings) is not list or any(type(w) is not str or len(w) > 180
                                          for w in warnings):
        raise RoomViewerError("Advertencias inválidas")
    if not isinstance(review.get("layout_sha256"), str) or not re.fullmatch(
            r"[0-9a-f]{64}", review["layout_sha256"]):
        raise RoomViewerError("Firma del layout inválida")
    return {"groups": clean_groups, "boxes": clean_boxes, "zones": clean_zones,
            "warnings": warnings, "status": review["status"],
            "digest": review["layout_sha256"]}


# Client-side isometric projection uses only verified world_boxes. No CDN,
# external assets, analytics, network calls, scripts or manufacturing endpoints.
_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CarpiNova · Inspector nominal 3D sin conexión</title>
<style>
:root{font-family:system-ui,Segoe UI,sans-serif;color:#e2e8f0;background:#0d1624}
*{box-sizing:border-box}body{margin:0}.top{padding:18px 24px;background:#152439;border-bottom:1px solid #314761}
h1{font-size:24px;margin:0 0 6px}.sub{font-size:13px;color:#a8bcd0;margin:0}.notice{color:#ffe3a0}
main{display:grid;grid-template-columns:minmax(0,1fr) 260px;min-height:calc(100vh - 90px)}
.stage{min-height:520px;background:radial-gradient(circle at 40% 20%,#1c3751,#09131f 80%);display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
#scene{width:100%;height:min(78vh,900px);min-height:480px;touch-action:pan-y}
.sidebar{background:#142236;border-left:1px solid #324358;padding:16px;display:flex;flex-direction:column;gap:15px}
fieldset{margin:0;border:1px solid #3a526a;border-radius:8px;padding:12px}legend{font-weight:650;font-size:14px}
button{background:#203f5d;color:white;border:1px solid #65829b;border-radius:6px;padding:8px 12px;cursor:pointer;margin:3px 3px 3px 0}
button[aria-pressed=true]{background:#126b87;border-color:#80d8e9}select{max-width:100%;width:100%;padding:8px;background:#203f5d;color:#fff;border:1px solid #65829b;border-radius:6px}button:focus-visible,input:focus-visible{outline:3px solid #ffd666;outline-offset:2px}
label{display:block;font-size:14px;margin:8px 0}input[type=range]{width:100%;accent-color:#30b0cf}
#details{background:#0e1b2b;border-radius:7px;padding:10px;min-height:90px;overflow-wrap:anywhere;font-size:13px}
.tag{font-family:monospace;font-size:11px;color:#89b2c5}svg polygon{cursor:pointer;stroke:#18283a;stroke-width:1.1;vector-effect:non-scaling-stroke}
svg polygon:focus-visible,svg polygon.selected{stroke:#fcd34d;stroke-width:3;outline:none}
svg text{font-family:system-ui,sans-serif;fill:#ccd9e5;font-size:11px;paint-order:stroke;stroke:#0d1624;stroke-width:3}
.warn{border-left:3px solid #eeb84e;padding-left:9px;color:#edcf89;font-size:12px;overflow-wrap:anywhere}
@media(max-width:800px){main{grid-template-columns:1fr}.sidebar{border-left:0;border-top:1px solid #324358}.stage{min-height:430px}#scene{min-height:410px;height:60vh}}
</style></head><body>
<header class="top"><h1>CarpiNova · Inspector 3D de revisión</h1>
<p class="sub"><strong class="notice">BORRADOR NOMINAL · NO CORTAR NI FABRICAR</strong> · 100 % sin conexión · geometría CADExchange existente</p>
<p class="sub">Escena <span id="digest" class="tag"></span> · <span id="status"></span></p></header>
<main><div class="stage"><svg id="scene" role="img" aria-label="Vista isométrica de los tableros nominales" viewBox="0 0 900 640"></svg></div>
<aside class="sidebar"><fieldset><legend>Orientación de revisión</legend><div id="views"></div>
<label>Altura de corte <output id="cutLabel"></output><input type="range" min="0" max="900" step="1" id="cut"></label>
<label>Ampliación <output id="zoomLabel">100 %</output><input type="range" min="60" max="160" step="10" value="100" id="zoom"></label>
<label><input type="checkbox" checked id="zones"> Mostrar reservas de servicio</label></fieldset>
<fieldset><legend>Módulos visibles</legend><div id="groups"></div></fieldset>
<fieldset><legend>Panel seleccionado</legend><label for="piecePicker">Elegir tablero (incluye los ocultos)</label><select id="piecePicker"></select><div id="details" aria-live="polite">Selecciona un tablero en la vista 3D.</div></fieldset>
<div class="warn">La representación es geométrica, no un plano de fabricación. No certifica cargas, anclajes, herrajes, holguras dinámicas ni uniones. Las reservas no crean perforaciones.</div>
<div id="warnings" class="warn"></div></aside></main>
<script id="scene-data" type="application/json">__SCENE_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('scene-data').textContent);
const NS='http://www.w3.org/2000/svg'; const svg=document.getElementById('scene');
const cut=document.getElementById('cut'),zoom=document.getElementById('zoom');
let heading=0,selected='',shown=new Set(data.groups.map(g=>g.id));
const E=(tag,attrs,text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n};
const palette=(role)=>role.startsWith('front_')||role==='drawer_facade'?['#b98a50','#d8ad72','#f5d5a0']:role.startsWith('back_')?['#5d8470','#83ac8b','#a9d1ae']:role.includes('tie')?['#607aab','#839fd0','#a9c2e6']:['#467b91','#6ca6bc','#a8d4df'];
const sw=(x,z)=>heading===0?[x,z]:heading===90?[z,-x]:heading===180?[-x,-z]:[-z,x];
const P=(x,y,z)=>{const [u,v]=sw(x,z);return [(u-v)*.83,(u+v)*.42-y*.97]};
const square=(b,side)=>{const [x,y,z]=b.origin,[w,h,d]=b.size,top=Math.min(y+h,Number(cut.value));if(top<=y)return null;const q=(a,c,e)=>P(a,c,e);
const faces=[[[x,y+top-y,z],[x+w,y+top-y,z],[x+w,y+top-y,z+d],[x,y+top-y,z+d]],
[[x+w,y,z],[x+w,y,z+d],[x+w,top,z+d],[x+w,top,z]],
[[x,y,z+d],[x+w,y,z+d],[x+w,top,z+d],[x,top,z+d]],
[[x,y,z],[x,y,z+d],[x,top,z+d],[x,top,z]],
[[x,y,z],[x+w,y,z],[x+w,top,z],[x,top,z]]];
const a=heading;let nearA,nearB;if(a===0){nearA=1;nearB=2}else if(a===90){nearA=2;nearB=3}else if(a===180){nearA=3;nearB=4}else{nearA=4;nearB=1}
return [faces[nearA],faces[nearB],faces[0]].map((points,i)=>({pts:points.map(([xx,yy,zz])=>q(xx,yy,zz)),fill:palette(side)[i]}));};
function render(){while(svg.firstChild)svg.removeChild(svg.firstChild);let all=[];const layer=E('g',{'id':'panels'});svg.appendChild(layer);
for(const box of data.boxes){if(!shown.has(box.group))continue;const parts=square(box,box.role);if(!parts)continue;const [x,y,z]=box.origin;const [w,h,d]=box.size;
const [u,v]=sw(x+w/2,z+d/2);all.push({depth:u+v,box,parts})}
all.sort((a,b)=>(a.box.id===selected?1:0)-(b.box.id===selected?1:0)||a.depth-b.depth);
const pts=[];
for(const entry of all){for(const face of entry.parts){const el=E('polygon',{'points':face.pts.map(p=>p.join(',')).join(' '),'fill':face.fill,'data-piece-id':entry.box.id,'data-role':entry.box.role,'tabindex':'0','class':selected===entry.box.id?'selected':''});el.appendChild(E('title',{},entry.box.id+' · '+entry.box.role));el.addEventListener('click',()=>pick(entry.box));el.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();pick(entry.box)}});layer.appendChild(el);face.pts.forEach(p=>pts.push(p))}}
if(document.getElementById('zones').checked){for(const zone of data.zones){if(zone.origin[1]>=Number(cut.value))continue;const q={origin:zone.origin,size:zone.size};const faces=square(q,'zone');if(!faces)continue;const g=E('g',{'opacity':'.22'});for(const face of faces){g.appendChild(E('polygon',{'points':face.pts.map(p=>p.join(',')).join(' '),'fill':'#ffbd68','stroke':'#e69925','stroke-dasharray':'4 3'}));face.pts.forEach(p=>pts.push(p))}layer.appendChild(g)}}
if(!pts.length){svg.setAttribute('viewBox','0 0 900 640');svg.appendChild(E('text',{x:30,y:50},'Sin paneles a esta altura o con filtros actuales.'));return}
const minx=Math.min(...pts.map(p=>p[0])),maxx=Math.max(...pts.map(p=>p[0])),miny=Math.min(...pts.map(p=>p[1])),maxy=Math.max(...pts.map(p=>p[1]));const sc=Number(zoom.value)/100;const w=Math.max(100,(maxx-minx)/sc),h=Math.max(100,(maxy-miny)/sc);const cx=(minx+maxx)/2,cy=(miny+maxy)/2;svg.setAttribute('viewBox',[cx-w/2-30,cy-h/2-30,w+60,h+60].join(' '));}
function pick(box){selected=box.id;document.getElementById('piecePicker').value=box.id;const e=document.getElementById('details');e.textContent=box.id+'\nGrupo: '+box.group+' · '+box.role+'\nOrigen XYZ: '+box.origin.join(', ')+' mm\nTamaño XYZ: '+box.size.join(' × ')+' mm';e.style.whiteSpace='pre-line';render()}
const maxHeight=Math.max(...data.groups.map(g=>g.origin[1]+g.size[1]));cut.max=String(maxHeight);cut.value=String(maxHeight);cutLabel.value=cut.value+' mm';document.getElementById('digest').textContent=data.digest.slice(0,12);document.getElementById('status').textContent=data.status;
for(const a of [0,90,180,270]){let b=document.createElement('button');b.textContent=a+'°';b.type='button';b.setAttribute('aria-pressed',String(a===0));b.addEventListener('click',()=>{heading=a;for(const b of document.querySelectorAll('#views button'))b.setAttribute('aria-pressed',String(b.textContent===a+'°'));render()});document.getElementById('views').appendChild(b)}
for(const g of data.groups){const row=document.createElement('label');const box=document.createElement('input');box.type='checkbox';box.checked=true;box.addEventListener('change',()=>{box.checked?shown.add(g.id):shown.delete(g.id);render()});row.append(box,document.createTextNode(' '+g.id+' ('+data.boxes.filter(b=>b.group===g.id).length+' tableros)'));document.getElementById('groups').appendChild(row)}
const warningText={'ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY':'Solo geometría nominal, sin autorización de corte','ROOM_LAYOUT_DOES_NOT_VERIFY_WALLS_LOADS_ANCHORS_OR_HARDWARE':'Muros, cargas, anclajes y herrajes sin verificar','SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION':'Reservas sin perforaciones ni instalación','CORNER_JOINT_AND_FILLER_NOT_DESIGNED':'Uniones y rellenos de esquina sin diseñar','OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL':'Interferencias entre muebles: aprobación bloqueada'};document.getElementById('warnings').textContent=data.warnings.map(w=>warningText[w]||w).join(' · ');
const picker=document.getElementById('piecePicker');for(const b of data.boxes){const o=document.createElement('option');o.value=b.id;o.textContent=b.id+' — '+b.role;picker.appendChild(o)}picker.selectedIndex=-1;picker.addEventListener('change',()=>pick(data.boxes.find(b=>b.id===picker.value)));
cut.addEventListener('input',()=>{cutLabel.value=cut.value+' mm';render()});zoom.addEventListener('input',()=>{document.getElementById('zoomLabel').textContent=zoom.value+' %';render()});document.getElementById('zones').addEventListener('change',render);render();
</script></body></html>
'''


def render_room_3d_html(review: dict[str, Any]) -> str:
    """Render a self-contained offline review from a verified room result."""
    payload = json.dumps(_payload(review), ensure_ascii=False, separators=(",", ":"))
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return _HTML.replace("__SCENE_DATA__", payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Visor isométrico nominal autónomo, sin CAD de taller")
    parser.add_argument("--input", type=Path, required=True,
                        help="Solicitud original room_layout_v1 con module_spec (NO CAD provisto)")
    parser.add_argument("--output", type=Path, required=True,
                        help="Ruta nueva para un único HTML offline")
    args = parser.parse_args(argv)
    if not args.input.is_file() or args.input.stat().st_size > _MAX_SIZE:
        parser.error("La solicitud no existe o excede el límite seguro")
    request = json.loads(args.input.read_text(encoding="utf-8"))
    if type(request) is not dict or request.get("review_kind") != "room_layout_v1":
        parser.error("Se requiere solicitud original room_layout_v1")
    # A client-supplied world_boxes/geometry payload is explicitly rejected.
    if set(request) != {"review_kind", "assemblies", "service_zones"}:
        parser.error("Solicitud con campos ajenos a Maestro: NO se acepta CAD del cliente")
    from .room_spatial import review_room_from_specs
    room = review_room_from_specs(request)
    html = render_room_3d_html(room)
    with args.output.open("x", encoding="utf-8") as f:
        f.write(html)
    print(f"D18=REVIEW_ONLY | HTML={args.output} | PIECES={len(room['world_boxes'])} | "
          f"ROOM_STATUS={room['status']} | RELEASE=NO_GO")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())