"""FreeCAD macro: Part geometry built solely from checked CAD contract.

Run only inside FreeCAD Python environment with the audited JSON file.
This is an optional local execution adapter, NOT an MCP server.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from carpinova_agent.cad_exchange import validate_exchange
from integrations.cad_native import native_boxes


def build_freecad(input_path: Path, output_path: Path)->dict:
    import FreeCAD as App  # only available within installed FreeCAD
    import Part
    if not output_path.is_absolute():
        raise ValueError("Output path must be absolute.")
    if output_path.suffix.lower() != ".fcstd":
        raise ValueError("Output must have .FCStd suffix.")
    data=validate_exchange(json.loads(input_path.read_text(encoding="utf-8")))
    doc=App.newDocument("CarpiNovaPreview")
    for piece in native_boxes(data):
        name=piece["piece_id"]
        x,y,z=piece["native_origin_xyz_mm"]
        dx,dy,dz=piece["native_size_xyz_mm"]
        feature=doc.addObject("PartDesign::Feature", "Panel")
        feature.Label=name
        feature.Shape=Part.makeBox(dx,dy,dz,App.Vector(x,y,z))
        if feature.Shape.isNull():
            raise ValueError("Null geometry for "+name)
    doc.recompute()
    doc.saveAs(str(output_path))
    return {"geometry_sha256":data["geometry_sha256"],"parts":len(data["boxes"]),
            "status":"CAD_PREVIEW_NOT_FOR_CUTTING"}


def main()->None:
    parser=argparse.ArgumentParser()
    parser.add_argument("--input",required=True,type=Path)
    parser.add_argument("--output",required=True,type=Path)
    options=parser.parse_args()
    print(json.dumps(build_freecad(options.input,options.output)))


if __name__=="__main__":
    main()
