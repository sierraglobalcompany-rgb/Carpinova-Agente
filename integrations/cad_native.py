"""Shared axis transform for both FreeCAD and Blender viewers.

CarpiNova: X right, Y up, Z back (mm).
CAD native: X right, Y forward, Z up, therefore (X,-Z,Y).
"""
from __future__ import annotations
from typing import Any

from carpinova_agent.cad_exchange import validate_exchange


def native_boxes(cad: dict[str,Any])->list[dict[str,Any]]:
    data=validate_exchange(cad)
    output=[]
    for box in data["boxes"]:
        x,y,z=box["origin_xyz_mm"]
        dx,dy,dz=box["size_xyz_mm"]
        output.append({
            "piece_id":box["piece_id"],
            "material_id":box["material_id"],
            "native_origin_xyz_mm":[x,-z-dz,y],
            "native_size_xyz_mm":[dx,dz,dy],
        })
    return output
