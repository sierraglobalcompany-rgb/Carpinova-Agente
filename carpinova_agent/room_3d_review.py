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
        clean_group = {"id": gid, "origin": origin, "size": size}
        if "rotation_deg" in item:
            rotation = item["rotation_deg"]
            if type(rotation) is not int or rotation not in {0, 90, 180, 270}:
                raise RoomViewerError("Rotación de grupo inválida")
            clean_group["rotation"] = rotation
        clean_groups.append(clean_group)
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
    construction = review.get("construction_review_by_group", {})
    if type(construction) is not dict or set(construction) - group_ids:
        raise RoomViewerError("Resumen de fondo y soporte inválido")
    valid_back = {"none", "pending", "inset_full", "inset_two_strips",
                  "unconfirmed", "mixed"}
    valid_support = {"REAR_WALL_SUPPORT_PENDING", "SUPPORT_PENDING",
                     "NOT_APPLICABLE", "mixed"}
    for group in clean_groups:
        item = construction.get(group["id"])
        if item is None:
            continue
        if (type(item) is not dict
                or set(item) != {"back_status", "wall_support_status",
                                 "wall_tie_mode", "install_ready", "module_count"}
                or type(item.get("back_status")) is not str
                or item.get("back_status") not in valid_back
                or type(item.get("wall_support_status")) is not str
                or item.get("wall_support_status") not in valid_support
                or type(item.get("wall_tie_mode")) is not str
                or item.get("wall_tie_mode") not in {
                    "NOT_IMPLEMENTED", "NOT_APPLICABLE",
                    "DIRECT_PAIR_CONCEPT_ONLY_UNVERIFIED"}
                or item.get("install_ready") is not False
                or type(item.get("module_count")) is not int
                or not 1 <= item["module_count"] <= 6):
            raise RoomViewerError("Resumen de fondo y soporte inseguro")
        group["construction"] = item

    drawer_suffix = {
        "drawer_side_left": "SIDE_LEFT",
        "drawer_side_right": "SIDE_RIGHT",
        "drawer_front_wall": "FRONT_WALL",
        "drawer_rear_wall": "REAR_WALL",
        "drawer_bottom": "BOTTOM",
        "drawer_facade": "FACADE",
    }
    drawer_groups: dict[str, list[dict[str, Any]]] = {}
    blocked_drawers: list[dict[str, str]] = []
    for box in clean_boxes:
        if not box["role"].startswith("drawer_") and "-DRAWER_" not in box["id"]:
            continue
        if "-DRAWER_" not in box["id"]:
            blocked_drawers.append({"id": box["id"], "group": box["group"],
                                    "reason": "ID sin separador -DRAWER_"})
            continue
        prefix, _suffix = box["id"].rsplit("-DRAWER_", 1)
        drawer_groups.setdefault(prefix, []).append(box)
    drawers = []
    expected_roles = set(drawer_suffix)
    for drawer_id, parts in sorted(drawer_groups.items()):
        role_counts = {role: sum(part["role"] == role for part in parts)
                       for role in expected_roles}
        groups_for_drawer = {part["group"] for part in parts}
        valid = (
            len(parts) == 6
            and len(groups_for_drawer) == 1
            and set(part["role"] for part in parts) == expected_roles
            and all(part["id"] == drawer_id + "-DRAWER_" + drawer_suffix[part["role"]]
                    for part in parts)
            and all(count == 1 for count in role_counts.values())
        )
        if not valid:
            blocked_drawers.append({
                "id": drawer_id,
                "group": next(iter(groups_for_drawer)) if len(groups_for_drawer) == 1 else "",
                "reason": "Se requieren seis roles e IDs originales distintos del mismo cajón",
            })
            continue
        min_z = min(part["origin"][2] for part in parts)
        max_z = max(part["origin"][2] + part["size"][2] for part in parts)
        if max_z <= min_z:
            blocked_drawers.append({"id": drawer_id, "group": parts[0]["group"],
                                    "reason": "Profundidad nominal inválida"})
            continue
        match = re.search(r"-(D[0-9]+)$", drawer_id)
        drawers.append({
            "id": drawer_id,
            "label": match.group(1) if match else drawer_id,
            "group": parts[0]["group"],
            "piece_ids": sorted(part["id"] for part in parts),
            "depth_mm": max_z - min_z,
        })
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
    return {"groups": clean_groups, "boxes": clean_boxes, "drawers": drawers,
            "blocked_drawers": blocked_drawers, "zones": clean_zones,
            "warnings": warnings, "status": review["status"],
            "digest": review["layout_sha256"]}


# Client-side isometric projection uses only verified world_boxes. No CDN,
# external assets, analytics, network calls, scripts or manufacturing endpoints.
_HTML = r'''<!doctype html>
<html lang="es"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>CarpiNova · Inspector nominal 3D sin conexión</title>
<style>
:root{font-family:system-ui,"Segoe UI",sans-serif;color:#172b3a;background:#edf2f4;line-height:1.45}
*{box-sizing:border-box}body{margin:0;min-width:0}.top{padding:20px clamp(16px,3vw,36px);background:#163746;color:#f3f7f8;border-bottom:4px solid #d9a441}
h1{font-size:clamp(20px,2.4vw,28px);line-height:1.2;margin:0 0 8px}.sub{font-size:13px;color:#d1e0e4;margin:4px 0}.notice{color:#ffdc91}
.summary{display:grid;grid-template-columns:repeat(auto-fit,minmax(min(100%,230px),1fr));gap:10px;padding:14px clamp(12px,2vw,24px);background:#fff;border-bottom:1px solid #cad5d9}
.summary-card{min-width:0;border-left:3px solid #21758a;padding:7px 10px;background:#f5f8f8;overflow-wrap:anywhere}.summary-card strong{display:block;font-size:12px;color:#375464}.summary-card span{font-size:14px;font-variant-numeric:tabular-nums}
main{display:grid;grid-template-columns:minmax(0,1fr) minmax(300px,360px);min-height:calc(100vh - 180px)}
.stage-wrap{min-width:0;padding:14px}.stage{min-height:500px;background:radial-gradient(circle at 42% 20%,#315469,#102530 82%);border-radius:10px;display:flex;align-items:center;justify-content:center;position:relative;overflow:hidden}
#scene{display:block;width:100%;height:min(72vh,820px);min-height:460px;touch-action:pan-y;cursor:grab;user-select:none}
.stage.dragging #scene{cursor:grabbing}
.stage-caption{font-size:12px;color:#526774;margin:9px 3px}.sidebar{background:#f6f8f8;border-left:1px solid #cad5d9;padding:14px;display:flex;flex-direction:column;gap:12px;min-width:0}
fieldset{margin:0;min-width:0;border:1px solid #c4d1d5;border-radius:8px;padding:11px;background:#fff}legend{font-weight:700;font-size:14px;padding:0 4px}
button{background:#e6eef0;color:#183745;border:1px solid #91a9b1;border-radius:6px;padding:8px 10px;cursor:pointer;margin:3px 4px 3px 0;font:inherit;font-size:13px}
button[aria-pressed=true]{background:#176b7d;border-color:#176b7d;color:#fff}button:hover{background:#d5e4e7}button[aria-pressed=true]:hover{background:#12596a}
select,input[type=number]{max-width:100%;width:100%;padding:8px;background:#fff;color:#17333f;border:1px solid #829aa2;border-radius:6px;font:inherit}button:focus-visible,input:focus-visible,select:focus-visible,svg polygon:focus-visible{outline:3px solid #c17c00;outline-offset:2px}
label{display:block;font-size:13px;margin:8px 0}.control-line{display:flex;align-items:flex-start;gap:8px}.control-line input{margin-top:4px;flex:0 0 auto}.control-note{display:block;color:#526974;font-size:12px;margin:4px 0}
#details{background:#f1f5f6;border:1px solid #d8e0e2;border-radius:7px;padding:10px;min-height:90px;overflow-wrap:anywhere;font-size:13px;white-space:pre-line}
.tag{font-family:ui-monospace,Consolas,monospace;font-size:12px;color:#9ed1dc}svg polygon{cursor:pointer;stroke:#15313c;stroke-width:1.1;vector-effect:non-scaling-stroke}
svg polygon:focus-visible,svg polygon.selected{stroke:#f5bc3d;stroke-width:3;outline:none}
svg text{font-family:system-ui,sans-serif;fill:#eef5f5;font-size:11px;paint-order:stroke;stroke:#102530;stroke-width:3}
.warn{border-left:3px solid #bd7c15;padding:7px 9px;background:#fff7e5;color:#624719;font-size:12px;overflow-wrap:anywhere}
.open-controls{margin:10px 0;background:#f5fafb}.door-control,.drawer-control{margin:8px 0;padding:6px 0;border-bottom:1px solid #d9e4e8}.door-control input[type=range],.drawer-control input[type=range]{width:100%}.door-control output,.drawer-control output{font-variant-numeric:tabular-nums;color:#0e6978;font-weight:700}
.interior-banner{padding:9px;border-radius:6px;background:#fff2cc;color:#624719;font-size:12px;font-weight:700}.empty-note{font-size:12px;color:#526974}
@media(max-width:850px){main{grid-template-columns:minmax(0,1fr)}.sidebar{border-left:0;border-top:1px solid #cad5d9}.stage-wrap{padding:10px}.stage{min-height:390px}#scene{min-height:370px;height:58vh}}
@media(max-width:420px){.summary{grid-template-columns:minmax(0,1fr)}.stage{min-height:340px}#scene{min-height:320px;height:48vh}.sidebar{padding:10px}.views{display:grid;grid-template-columns:repeat(4,minmax(0,1fr))}.views button{padding:7px 3px;margin:2px 2px 2px 0}}
</style></head><body>
<header class="top"><h1>CarpiNova · VISOR NOMINAL SIN AUTORIZACIÓN DE FABRICACIÓN</h1>
<p class="sub"><strong class="notice">Ejemplo de revisión, no proyecto para fabricar</strong> · Vista geométrica 2.5D simplificada · 100 % sin conexión</p>
<p class="sub">Estado <span id="status"></span> · SHA de escena <span id="digest" class="tag"></span></p></header>
<section class="summary" aria-label="Resumen dimensional de revisión">
<div class="summary-card"><strong>Conjunto nominal</strong><span id="sceneName"></span></div>
<div class="summary-card"><strong>Envolvente CAD global</strong><span id="globalBounds"></span></div>
<div class="summary-card"><strong>Paneles nominales</strong><span id="sceneCount"></span></div>
<div class="summary-card"><strong>Grupos</strong><span id="groupSummary"></span></div>
</section>
<main><section class="stage-wrap"><div class="stage"><svg id="scene" role="img" aria-label="Vista nominal simplificada 2.5D; no valida ensamble" viewBox="0 0 900 640"></svg></div>
<p class="stage-caption"><strong>Arrastra sobre el mueble para girar · rueda para ampliar.</strong> La proyección puede simplificar oclusiones y uniones. Cambiar la vista solo mueve la cámara; no modifica piezas ni valida el ensamble.</p></section>
<aside class="sidebar"><fieldset><legend>Vista y controles visuales</legend><span class="control-note">Orientación — solo cámara</span><div id="views" class="views"></div>
<span id="cameraReadout" class="control-note" aria-live="polite">Giro 0° · Elevación 35°</span>
<label class="control-line"><input type="checkbox" id="interior"><span>Inspeccionar interior (oculta frentes de puertas; conserva tapas y repisas)</span></label>
<fieldset id="openingGroup" class="open-controls"><legend>Abrir puertas nominales</legend>
<div id="doorSliders"></div><div id="noDoors" class="empty-note" hidden>Esta escena no tiene puertas abatibles con lados identificables.</div>
<div id="drawerSliders"></div><div id="noDrawers" class="empty-note" hidden>Este ejemplo no contiene cajones completos para abrir.</div>
<div id="blockedDrawers" class="empty-note" hidden></div>
<div class="control-note">Movimiento visual ilustrativo (0–90°). Sin bisagras, holguras de giro ni cargas verificadas. No altera las piezas CAD.</div>
<div class="control-note">Apertura de cajón nominal e ilustrativa; no valida riel, cargas, colisiones dinámicas, holguras ni perforaciones.</div>
</fieldset>
<div id="interiorBanner" class="interior-banner" hidden>VISTA INTERIOR: solo se ocultan visualmente los frentes de puertas; tapas, bases, repisas, laterales, fondos y piezas drawer_* permanecen en escena y en los datos.</div>
<div id="noShelf" class="empty-note" hidden>Este modelo no contiene repisa.</div>
<label for="cutEnabled" class="control-line"><input type="checkbox" id="cutEnabled"><span id="cutState">Corte OFF</span></label>
<label for="cutHeight">Altura límite Y (mm)<input type="number" id="cutHeight" step="1" min="0" disabled></label>
<span class="control-note">Corte de visualización simplificada; no altera el modelo.</span>
<label for="zoom">Ampliación <output id="zoomLabel">100 %</output><input type="range" min="60" max="160" step="10" value="100" id="zoom"></label>
<label id="zoneControl" for="zones" hidden><input type="checkbox" checked id="zones"> Mostrar reservas de servicio (no son perforaciones)</label>
<button type="button" id="resetView">Restablecer vista completa</button></fieldset>
<fieldset><legend>Grupos visibles</legend><div id="groups"></div></fieldset>
<fieldset><legend>Panel seleccionado</legend><label for="piecePicker">Elegir tablero (incluye los ocultos)</label><select id="piecePicker"></select><div id="details" aria-live="polite">Selecciona un tablero para ver sus medidas nominales.</div></fieldset>
<div class="warn"><strong>APERTURA VISUAL NOMINAL · NO FABRICAR / NO CORTAR / NO PERFORAR / NO COMPRAR.</strong> La proyección y aperturas son ILUSTRATIVAS, no CAD sólido ni plano de fabricación. No validan bisagras, correderas, cargas, anclajes, holguras dinámicas, instalación ni accesibilidad física. Las reservas no crean agujeros.</div>
<div id="warnings" class="warn"></div></aside></main>
<script id="scene-data" type="application/json">__SCENE_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('scene-data').textContent);
const NS='http://www.w3.org/2000/svg'; const svg=document.getElementById('scene');
const cutEnabled=document.getElementById('cutEnabled'),cutHeight=document.getElementById('cutHeight'),zoom=document.getElementById('zoom');
const INITIAL_ELEVATION=35;
let yaw=0,elevation=INITIAL_ELEVATION,activePreset=0,selected='',shown=new Set(data.groups.map(g=>g.id));
const doorAngles=new Map(),drawerProgress=new Map(),drawerByPiece=new Map();
for(const drawer of data.drawers){for(const id of drawer.piece_ids)drawerByPiece.set(id,drawer)}
const E=(tag,attrs,text)=>{const n=document.createElementNS(NS,tag);for(const [k,v] of Object.entries(attrs||{}))n.setAttribute(k,String(v));if(text!==undefined)n.textContent=text;return n};
const palette=(role)=>role.startsWith('front_')||role==='drawer_facade'?['#b98a50','#d8ad72','#f5d5a0']:role.startsWith('back_')?['#5d8470','#83ac8b','#a9d1ae']:role.includes('tie')?['#607aab','#839fd0','#a9c2e6']:['#467b91','#6ca6bc','#a8d4df'];
const clamp=(value,min,max)=>Math.min(max,Math.max(min,value));
const normalizeYaw=value=>((value%360)+360)%360;
const cameraState=()=>{const az=(45-yaw)*Math.PI/180,el=elevation*Math.PI/180,ce=Math.cos(el),se=Math.sin(el);return {position:[Math.sin(az)*ce,se,-Math.cos(az)*ce],right:[Math.cos(az),0,Math.sin(az)],up:[-Math.sin(az)*se,ce,Math.cos(az)*se]}};
const dot=(a,b)=>a[0]*b[0]+a[1]*b[1]+a[2]*b[2];
const P=(x,y,z)=>{const c=cameraState(),d=[x-pivot[0],y-pivot[1],z-pivot[2]];return [dot(c.right,d),-dot(c.up,d)]};
const ROLE_LABEL={front_left:'puerta izquierda nominal',front_right:'puerta derecha nominal',front_corner_blind:'panel ciego NO puerta',front_corner_access:'puerta nominal sin bisagra validada',shelf_horizontal:'repisa',top:'tapa',bottom:'base',left_side:'lateral izquierdo',right_side:'lateral derecho',back_full:'fondo completo'};
const labelRole=role=>ROLE_LABEL[role]||role;
const maxHeight=Math.max(...data.groups.map(g=>g.origin[1]+g.size[1]));
cutHeight.max=String(maxHeight);cutHeight.value=String(maxHeight);
const mins=[0,1,2].map(i=>Math.min(...data.groups.map(g=>g.origin[i])));
const maxs=[0,1,2].map(i=>Math.max(...data.groups.map(g=>g.origin[i]+g.size[i])));
const pivot=mins.map((value,i)=>(value+maxs[i])/2);
// Keep a fixed camera frame that includes door swings and the conservative visual drawer travel.
const frameMin=mins.slice(),frameMax=maxs.slice();
const includeFramePoint=point=>{for(let i=0;i<3;i++){frameMin[i]=Math.min(frameMin[i],point[i]);frameMax[i]=Math.max(frameMax[i],point[i])}};
for(const box of data.boxes.filter(item=>item.role==='front_left'||item.role==='front_right')){
 const [x,y,z]=box.origin,[w,h,d]=box.size,isLeft=box.role==='front_left',hx=isLeft?x:x+w,hz=z+d/2,turn=isLeft?1:-1;
 for(const xx of [x,x+w])for(const yy of [y,y+h])for(const zz of [z,z+d])for(let deg=0;deg<=90;deg++){
  const a=turn*deg*Math.PI/180,c=Math.cos(a),s=Math.sin(a),dx=xx-hx,dz=zz-hz;
  includeFramePoint([hx+dx*c+dz*s,yy,hz-dx*s+dz*c]);
 }
}
for(const drawer of data.drawers){
 const travel=drawer.depth_mm*.2;
 for(const box of data.boxes.filter(item=>drawer.piece_ids.includes(item.id))){
  includeFramePoint([box.origin[0],box.origin[1],box.origin[2]-travel]);
  includeFramePoint([box.origin[0]+box.size[0],box.origin[1]+box.size[1],box.origin[2]+box.size[2]-travel]);
 }
}
const axes=['X (horizontal)','Y (vertical)','Z (fondo)'];
document.getElementById('globalBounds').textContent=axes.map((axis,i)=>`${axis}: ${mins[i]}–${maxs[i]} (${maxs[i]-mins[i]} mm)`).join(' · ');
document.getElementById('sceneName').textContent=data.groups.map(g=>g.id).join(' · ');
document.getElementById('sceneCount').textContent=`${data.boxes.length} paneles · ${data.status}`;
document.getElementById('groupSummary').textContent=data.groups.map(g=>{const c=g.construction;const state=c?`; fondo ${c.back_status}; soporte ${c.wall_support_status}; amarre ${c.wall_tie_mode}; instalación no liberada`:'';return `${g.id}: origen ${g.origin.join(', ')} mm; bounds ${g.size.join(' × ')} mm; ${data.boxes.filter(b=>b.group===g.id).length} piezas${Number.isInteger(g.rotation)?`; rotación ${g.rotation}°`:''}${state}`}).join(' | ');
document.getElementById('digest').textContent=data.digest.slice(0,12);
document.getElementById('status').textContent=data.status;
const updateCut=()=>{cutHeight.disabled=!cutEnabled.checked;document.getElementById('cutState').textContent=cutEnabled.checked?`CORTE ACTIVADO · hasta Y=${cutHeight.value} mm`:'Corte OFF'};
const square=(b,side)=>{const [x,y,z]=b.origin,[w,h,d]=b.size,top=cutEnabled.checked?Math.min(y+h,Number(cutHeight.value)):y+h;if(top<=y)return null;
const faces=[[[x,top,z],[x+w,top,z],[x+w,top,z+d],[x,top,z+d]],
[[x+w,y,z],[x+w,y,z+d],[x+w,top,z+d],[x+w,top,z]],
[[x,y,z+d],[x+w,y,z+d],[x+w,top,z+d],[x,top,z+d]],
[[x,y,z],[x,y,z+d],[x,top,z+d],[x,top,z]],
[[x,y,z],[x+w,y,z],[x+w,top,z],[x,top,z]],
[[x,y,z],[x+w,y,z],[x+w,y,z+d],[x,y,z+d]]];
const normals=[[0,1,0],[1,0,0],[0,0,1],[-1,0,0],[0,0,-1],[0,-1,0]],camera=cameraState();
return faces.flatMap((points,index)=>{if(dot(normals[index],camera.position)<=0.00001)return [];return [{pts:points.map(([xx,yy,zz])=>P(xx,yy,zz)),world:points,faceIndex:index,fill:palette(side)[index===0?2:index===1||index===2?1:0]}]})};
// Orthographic rigid-body display ONLY: no hinge SKU, motion-clearance or load validation.
// A front-left leaf pivots around its left x-edge; a front-right leaf around its right.
const hingeFaces=(box, angleDeg)=>{
 const [x,y,z]=box.origin,[w,h,d]=box.size;
 const isLeft=box.role==='front_left';
 const hingeX=isLeft?x:x+w, hingeZ=z+d/2;
 const theta=(isLeft?1:-1)*angleDeg*Math.PI/180;
 const c=Math.cos(theta),si=Math.sin(theta);
 const R=([xx,yy,zz])=>{const dx=xx-hingeX,dz=zz-hingeZ;
  return [hingeX+dx*c+dz*si,yy,hingeZ-dx*si+dz*c];};
 const original=[
 // top, right, back, left, front, bottom: plane indices stable
 [[x,y+h,z],[x+w,y+h,z],[x+w,y+h,z+d],[x,y+h,z+d]],
 [[x+w,y,z],[x+w,y,z+d],[x+w,y+h,z+d],[x+w,y+h,z]],
 [[x,y,z+d],[x+w,y,z+d],[x+w,y+h,z+d],[x,y+h,z+d]],
 [[x,y,z],[x,y,z+d],[x,y+h,z+d],[x,y+h,z]],
 [[x,y,z],[x+w,y,z],[x+w,y+h,z],[x,y+h,z]],
 [[x,y,z],[x+w,y,z],[x+w,y,z+d],[x,y,z+d]]
 ];
 const normals=[[0,1,0],[1,0,0],[0,0,1],[-1,0,0],[0,0,-1],[0,-1,0]];
  const camera=cameraState(),fills=palette(box.role);
 return original.flatMap((face,index)=>{
  const [nx,ny,nz]=normals[index];
  const rx=nx*c+nz*si,rz=-nx*si+nz*c;
   if(dot([rx,ny,rz],camera.position)<=0.00001)return [];
  const world=face.map(R);
  return [{pts:world.map(([xx,yy,zz])=>P(xx,yy,zz)),world,faceIndex:index,
   fill:index===0?fills[2]:index===4?fills[0]:index===2?fills[1]:fills[1]}];
 });
};
const updateViewBox=()=>{const corners=[];for(const x of [frameMin[0],frameMax[0]])for(const y of [frameMin[1],frameMax[1]])for(const z of [frameMin[2],frameMax[2]])corners.push(P(x,y,z));const halfW=(Math.max(...corners.map(p=>Math.abs(p[0])))+30)*100/Number(zoom.value),halfH=(Math.max(...corners.map(p=>Math.abs(p[1])))+30)*100/Number(zoom.value);svg.setAttribute('viewBox',[-halfW,-halfH,halfW*2,halfH*2].join(' '))};

const MAX_RASTER_PIXELS=1000000;
let pickBuffer=null,baseWarnings=null;
const viewerUnavailable=reason=>{
 pickBuffer=null;
 document.getElementById('status').textContent='VISOR_NO_DISPONIBLE';
 const warnings=document.getElementById('warnings');
 warnings.textContent=[baseWarnings,'VISOR_NO_DISPONIBLE: '+reason].filter(Boolean).join(' · ');
 svg.appendChild(E('text',{x:-120,y:0,'role':'alert'},'VISOR_NO_DISPONIBLE · '+reason));
};
function render(){
 while(svg.firstChild)svg.removeChild(svg.firstChild);
 const warnings=document.getElementById('warnings');
 if(baseWarnings===null)baseWarnings=warnings.textContent;
 warnings.textContent=baseWarnings;
 document.getElementById('status').textContent=data.status;
 const all=[],layer=E('g',{'id':'panels'});svg.appendChild(layer);
 for(let boxIndex=0;boxIndex<data.boxes.length;boxIndex++){
  const original=data.boxes[boxIndex];if(!shown.has(original.group))continue;
  if(document.getElementById('interior').checked&&original.role.startsWith('front_'))continue;
  const drawer=drawerByPiece.get(original.id),progress=drawer?drawerProgress.get(drawer.id)||0:0;
  const box=progress?{...original,origin:[original.origin[0],original.origin[1],original.origin[2]-drawer.depth_mm*.2*progress/100]}:original;
  const angle=doorAngles.get(box.id)||0,parts=angle>0?hingeFaces(box,angle):square(box,box.role);
  if(!parts)continue;
  for(const face of parts)all.push({boxIndex,faceId:boxIndex*6+face.faceIndex,box,face});
 }
 updateViewBox();
 if(!all.length){pickBuffer=null;svg.appendChild(E('text',{x:-120,y:0},'Sin paneles a esta altura o con filtros actuales.'));return;}
 const vb=svg.viewBox.baseVal,width=720;
 if(!Number.isFinite(vb.width)||!Number.isFinite(vb.height)||vb.width<=0||vb.height<=0){viewerUnavailable('encuadre inválido');return;}
 const height=Math.max(100,Math.round(width*vb.height/vb.width)),pixelCount=width*height;
 if(!Number.isSafeInteger(pixelCount)||pixelCount>MAX_RASTER_PIXELS){viewerUnavailable('límite de imagen superado');return;}
 let depth,owners,faceIds,canvas,ctx,imageData;
 try{
  depth=new Float32Array(pixelCount);depth.fill(-Infinity);
  owners=new Int16Array(pixelCount);owners.fill(-1);
  faceIds=new Int16Array(pixelCount);faceIds.fill(-1);
  canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;
  ctx=canvas.getContext('2d',{alpha:true});
  if(!ctx)throw new Error('Canvas 2D unavailable');
  imageData=ctx.createImageData(width,height);
 }catch(error){viewerUnavailable('memoria o Canvas 2D no disponible');return;}
 const faceColors=[],camera=cameraState();
 for(const entry of all){
  const vertices=entry.face.pts.map(([x,y])=>[(x-vb.x)/vb.width*width,(y-vb.y)/vb.height*height]);
  const distances=entry.face.world.map(point=>dot([point[0]-pivot[0],point[1]-pivot[1],point[2]-pivot[2]],camera.position));
  faceColors[entry.faceId]=paintFaceHex(entry.face.fill);
  for(const triangle of [[0,1,2],[0,2,3]]){
   const [a,b,c]=triangle.map(index=>vertices[index]);
   const [da,db,dc]=triangle.map(index=>distances[index]);
   const area=(b[0]-a[0])*(c[1]-a[1])-(b[1]-a[1])*(c[0]-a[0]);
   if(Math.abs(area)<1e-8)continue;
   const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(width-1,Math.ceil(Math.max(a[0],b[0],c[0])));
   const y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(height-1,Math.ceil(Math.max(a[1],b[1],c[1])));
   for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
    const px=x+.5,py=y+.5;
    const wa=((b[0]-px)*(c[1]-py)-(b[1]-py)*(c[0]-px))/area;
    if(wa < -1e-8)continue;
    const wb=((c[0]-px)*(a[1]-py)-(c[1]-py)*(a[0]-px))/area;
    if(wb < -1e-8)continue;
    const wc=1-wa-wb;if(wc < -1e-8)continue;
    const index=y*width+x,value=wa*da+wb*db+wc*dc;
    if(value>depth[index]+1e-5){depth[index]=value;owners[index]=entry.boxIndex;faceIds[index]=entry.faceId;}
   }
  }
 }
 const rgba=imageData.data;
 for(let y=0;y<height;y++)for(let x=0;x<width;x++){
  const index=y*width+x,face=faceIds[index];if(face<0)continue;
  const base=faceColors[face],offset=index*4;
  const edge=(x>0&&faceIds[index-1]!==face)||(x+1<width&&faceIds[index+1]!==face)
   ||(y>0&&faceIds[index-width]!==face)||(y+1<height&&faceIds[index+width]!==face);
  const color=edge?[15,46,60]:base,selectedPiece=data.boxes[owners[index]].id;
  if(selected===selectedPiece&&edge){rgba[offset]=249;rgba[offset+1]=209;rgba[offset+2]=84;}
  else{rgba[offset]=color[0];rgba[offset+1]=color[1];rgba[offset+2]=color[2];}
  rgba[offset+3]=255;
 }
 try{
  ctx.putImageData(imageData,0,0);
  const dataUrl=canvas.toDataURL('image/png');
  if(dataUrl==='data:,')throw new Error('Canvas PNG unavailable');
  const image=E('image',{x:vb.x,y:vb.y,width:vb.width,height:vb.height,
   href:dataUrl,'data-depth-tested':'true','data-piece-count':data.boxes.length});
  layer.appendChild(image);
 }catch(error){viewerUnavailable('falló el dibujo Canvas 2D');return;}
 pickBuffer={width,height,ids:owners,x:vb.x,y:vb.y,w:vb.width,h:vb.height};
 if(data.zones.length&&document.getElementById('zones').checked){
  for(const zone of data.zones){
   if(cutEnabled.checked&&zone.origin[1]>=Number(cutHeight.value))continue;
   const faces=square({origin:zone.origin,size:zone.size},'zone');if(!faces)continue;
   const group=E('g',{'opacity':'.42','data-zone-id':zone.id});
   for(const face of faces)group.appendChild(E('polygon',{'points':face.pts.map(point=>point.join(',')).join(' '),'fill':'#ffbd68','stroke':'#a45f00','stroke-dasharray':'4 3'}));
   layer.appendChild(group);
  }
 }
}
const paintFaceHex=hex=>[parseInt(hex.slice(1,3),16),parseInt(hex.slice(3,5),16),parseInt(hex.slice(5,7),16)];
const panelAt=(x,y)=>{
 if(!pickBuffer)return null;
 const matrix=svg.getScreenCTM();if(!matrix)return null;
 const determinant=matrix.a*matrix.d-matrix.b*matrix.c;
 if(!Number.isFinite(determinant)||Math.abs(determinant)<1e-12)return null;
 try{
  const point=svg.createSVGPoint();point.x=x;point.y=y;
  const hit=point.matrixTransform(matrix.inverse());
  const ix=Math.floor((hit.x-pickBuffer.x)/pickBuffer.w*pickBuffer.width);
  const iy=Math.floor((hit.y-pickBuffer.y)/pickBuffer.h*pickBuffer.height);
  if(ix<0||iy<0||ix>=pickBuffer.width||iy>=pickBuffer.height)return null;
  const owner=pickBuffer.ids[iy*pickBuffer.width+ix];
  return owner>=0&&owner<data.boxes.length?data.boxes[owner].id:null;
 }catch(error){return null;}
};
function pick(box){selected=box.id;document.getElementById('piecePicker').value=box.id;const e=document.getElementById('details');e.textContent=`${box.id}\nGrupo: ${box.group}\nRol: ${labelRole(box.role)} (${box.role})\nOrigen XYZ: ${box.origin.join(', ')} mm\nTamaño XYZ: ${box.size.join(' × ')} mm`;render()}
const updateCameraReadout=()=>{document.getElementById('cameraReadout').textContent=`Giro ${Math.round(yaw)}° · Elevación ${Math.round(elevation)}°`;for(const button of document.querySelectorAll('#views button'))button.setAttribute('aria-pressed',String(activePreset!==null&&Number(button.dataset.yaw)===activePreset&&elevation===INITIAL_ELEVATION))};
for(const angle of [0,90,180,270]){const button=document.createElement('button');button.textContent=angle+'°';button.dataset.yaw=String(angle);button.type='button';button.setAttribute('aria-label',`Solo cámara: orientación ${angle} grados`);button.addEventListener('click',()=>{yaw=angle;elevation=INITIAL_ELEVATION;activePreset=angle;updateCameraReadout();render()});document.getElementById('views').appendChild(button)}updateCameraReadout();
const stage=document.querySelector('.stage');let pointerDrag=null,suppressClickUntil=0;
const finishPointer=(event,allowSelection)=>{if(!pointerDrag||pointerDrag.id!==event.pointerId)return;const drag=pointerDrag;pointerDrag=null;stage.classList.remove('dragging');if(drag.moved){suppressClickUntil=performance.now()+250;setTimeout(()=>{suppressClickUntil=0},0)}else if(allowSelection&&drag.pieceId&&panelAt(event.clientX,event.clientY)===drag.pieceId){const box=data.boxes.find(item=>item.id===drag.pieceId);if(box)pick(box)}};
svg.addEventListener('pointerdown',event=>{if(event.button!==0||!event.isPrimary)return;pointerDrag={id:event.pointerId,x:event.clientX,y:event.clientY,yaw,elevation,pieceId:panelAt(event.clientX,event.clientY),moved:false};svg.setPointerCapture(event.pointerId)});
svg.addEventListener('pointermove',event=>{if(!pointerDrag||pointerDrag.id!==event.pointerId)return;const dx=event.clientX-pointerDrag.x,dy=event.clientY-pointerDrag.y;if(!pointerDrag.moved&&Math.hypot(dx,dy)<5)return;pointerDrag.moved=true;event.preventDefault();yaw=normalizeYaw(pointerDrag.yaw+dx*.5);elevation=clamp(pointerDrag.elevation-dy*.35,15,75);activePreset=null;stage.classList.add('dragging');updateCameraReadout();render()});
svg.addEventListener('pointerup',event=>finishPointer(event,true));svg.addEventListener('pointercancel',event=>finishPointer(event,false));svg.addEventListener('lostpointercapture',event=>finishPointer(event,false));
svg.addEventListener('click',event=>{if(performance.now()<=suppressClickUntil){event.preventDefault();event.stopImmediatePropagation();suppressClickUntil=0}},true);
svg.addEventListener('wheel',event=>{if(event.deltaY===0)return;event.preventDefault();const value=clamp(Number(zoom.value)+(event.deltaY<0?10:-10),60,160);if(value===Number(zoom.value))return;zoom.value=String(value);document.getElementById('zoomLabel').textContent=value+' %';render()},{passive:false});
for(const group of data.groups){const row=document.createElement('label'),box=document.createElement('input');box.type='checkbox';box.checked=true;box.addEventListener('change',()=>{box.checked?shown.add(group.id):shown.delete(group.id);render()});row.append(box,document.createTextNode(` ${group.id} (${data.boxes.filter(b=>b.group===group.id).length} paneles)`));document.getElementById('groups').appendChild(row)}
const warningText={'ALL_GEOMETRY_NOMINAL_NO_CUT_AUTHORITY':'Geometría nominal, sin autorización de corte','ROOM_LAYOUT_DOES_NOT_VERIFY_WALLS_LOADS_ANCHORS_OR_HARDWARE':'Muros, cargas, anclajes y herrajes sin verificar','SERVICE_RESERVATIONS_ARE_NOT_HOLES_OR_PLUMBING_INSTALLATION':'Reservas sin perforaciones ni instalación','CORNER_JOINT_AND_FILLER_NOT_DESIGNED':'Uniones y rellenos de esquina sin diseñar','OVERLAPPING_CABINET_ENVELOPES_BLOCK_APPROVAL':'Interferencias entre muebles: aprobación bloqueada'};
document.getElementById('warnings').textContent=data.warnings.map(w=>warningText[w]||w).join(' · ');
const picker=document.getElementById('piecePicker');for(const box of data.boxes){const option=document.createElement('option');option.value=box.id;option.textContent=`${box.id} — ${labelRole(box.role)} (${box.role})`;picker.appendChild(option)}picker.selectedIndex=-1;
picker.addEventListener('change',()=>pick(data.boxes.find(box=>box.id===picker.value)));
// Only actual front-left/right panels get movement controls. Fixed blind panels
// and missing drawers are never invented or animated.
const movable=data.boxes.filter(box=>box.role==='front_left'||box.role==='front_right');
document.getElementById('noDoors').hidden=movable.length>0;
document.getElementById('noDrawers').hidden=data.drawers.length>0;
const blocked=document.getElementById('blockedDrawers');
if(data.blocked_drawers.length){blocked.hidden=false;blocked.textContent='Cajones bloqueados para apertura visual: '+data.blocked_drawers.map(item=>`${item.id}: ${item.reason}`).join(' · ')}
for(const drawer of data.drawers){
 const row=document.createElement('div');row.className='drawer-control';row.dataset.drawerId=drawer.id;
 const label=document.createElement('label');const title=document.createElement('strong');
 title.textContent=`${drawer.label} · ${drawer.group}`;
 const output=document.createElement('output');output.textContent='0 % (cerrado)';
 const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='100';slider.step='10';slider.value='0';
 slider.dataset.drawerId=drawer.id;
 slider.setAttribute('aria-label',`Apertura visual nominal de ${drawer.label} en ${drawer.group}`);
 slider.addEventListener('input',()=>{const value=Number(slider.value);drawerProgress.set(drawer.id,value);output.textContent=`${value} % ${value===0?'(cerrado)':'(solo ilustración)'}`;render()});
 label.append(title,document.createTextNode(' '),output);row.append(label,slider);document.getElementById('drawerSliders').appendChild(row);
}
for(const box of movable){
 const row=document.createElement('div');row.className='door-control';
 const label=document.createElement('label');
 const title=document.createElement('strong');title.textContent=labelRole(box.role)+' · '+box.group;
 const output=document.createElement('output');output.textContent='0° (cerrada)';
 const slider=document.createElement('input');slider.type='range';slider.min='0';slider.max='90';slider.step='10';slider.value='0';
 slider.setAttribute('aria-label','Apertura visual de '+labelRole(box.role)+' de '+box.group);
 slider.addEventListener('input',()=>{
  const a=Number(slider.value);doorAngles.set(box.id,a);
  output.textContent=a+'° '+(a===0?'(cerrada)':'(solo ilustración)');
  document.getElementById('interior').checked=false;
  document.getElementById('interiorBanner').hidden=true;
  render();
 });
 label.append(title,document.createTextNode(' '),output);row.append(label,slider);
 document.getElementById('doorSliders').appendChild(row);
}

cutEnabled.addEventListener('change',()=>{updateCut();render()});cutHeight.addEventListener('input',()=>{const valid=cutHeight.value!==''&&Number(cutHeight.value)>=0&&Number(cutHeight.value)<=maxHeight;if(valid){updateCut();render()}});
zoom.addEventListener('input',()=>{document.getElementById('zoomLabel').textContent=zoom.value+' %';render()});
document.getElementById('interior').addEventListener('change',event=>{const enabled=event.target.checked;document.getElementById('interiorBanner').hidden=!enabled;document.getElementById('noShelf').hidden=!(enabled&&!data.boxes.some(box=>box.role==='shelf_horizontal'));render()});
if(data.zones.length){document.getElementById('zoneControl').hidden=false;document.getElementById('zones').addEventListener('change',render)}
document.getElementById('resetView').addEventListener('click',()=>{yaw=0;elevation=INITIAL_ELEVATION;activePreset=0;updateCameraReadout();zoom.value='100';cutEnabled.checked=false;cutHeight.value=String(maxHeight);shown=new Set(data.groups.map(group=>group.id));for(const input of document.querySelectorAll('#groups input[type=checkbox]'))input.checked=true;document.getElementById('interior').checked=false;document.getElementById('interiorBanner').hidden=true;document.getElementById('noShelf').hidden=true;if(data.zones.length)document.getElementById('zones').checked=true;selected='';picker.selectedIndex=-1;document.getElementById('details').textContent='Selecciona un tablero para ver sus medidas nominales.';document.getElementById('zoomLabel').textContent='100 %';doorAngles.clear();drawerProgress.clear();for(const input of document.querySelectorAll('#doorSliders input')){input.value='0';input.previousElementSibling?.querySelector('output')?.replaceChildren('0° (cerrada)')}for(const input of document.querySelectorAll('#drawerSliders input')){input.value='0';input.previousElementSibling?.querySelector('output')?.replaceChildren('0 % (cerrado)')}updateCut();render()});
updateCut();render();
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
