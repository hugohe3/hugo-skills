"""Ensure the vendored SmartArt reader resolves package parts independently."""

import io
import sys
import unittest
import zipfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from _smartart import read_smartart_diagrams, smartart_to_markdown


class StandaloneSmartArtTests(unittest.TestCase):
    def test_nodes_and_parent_connection_survive_readback(self):
        a = "http://schemas.openxmlformats.org/drawingml/2006/main"
        p = "http://schemas.openxmlformats.org/presentationml/2006/main"
        r = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
        d = "http://schemas.openxmlformats.org/drawingml/2006/diagram"
        slide = f'''<p:sld xmlns:p="{p}" xmlns:a="{a}" xmlns:r="{r}" xmlns:dgm="{d}">
          <p:cSld><p:spTree><p:graphicFrame>
          <p:nvGraphicFramePr><p:cNvPr id="4" name="Workflow"/></p:nvGraphicFramePr>
          <a:graphic><a:graphicData uri="{d}">
          <dgm:relIds r:dm="rId1"/></a:graphicData></a:graphic>
          </p:graphicFrame></p:spTree></p:cSld></p:sld>'''
        data = f'''<dgm:dataModel xmlns:dgm="{d}" xmlns:a="{a}">
          <dgm:ptLst>
          <dgm:pt modelId="parent" type="node"><dgm:t><a:p><a:r><a:t>Parent</a:t></a:r></a:p></dgm:t></dgm:pt>
          <dgm:pt modelId="child" type="node"><dgm:t><a:p><a:r><a:t>Child</a:t></a:r></a:p></dgm:t></dgm:pt>
          </dgm:ptLst><dgm:cxnLst>
          <dgm:cxn modelId="edge" type="parOf" srcId="parent" destId="child" srcOrd="0"/>
          </dgm:cxnLst></dgm:dataModel>'''
        rels = f'''<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
          <Relationship Id="rId1" Type="{r}/diagramData" Target="../diagrams/data1.xml"/>
          </Relationships>'''
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as package:
            package.writestr("ppt/slides/slide1.xml", slide)
            package.writestr("ppt/slides/_rels/slide1.xml.rels", rels)
            package.writestr("ppt/diagrams/data1.xml", data)
        with zipfile.ZipFile(stream) as package:
            diagrams = read_smartart_diagrams(package, "ppt/slides/slide1.xml", 1)
        self.assertEqual(len(diagrams), 1)
        self.assertEqual(diagrams[0]["status"], "ok")
        self.assertEqual(diagrams[0]["node_count"], 2)
        self.assertEqual(diagrams[0]["nodes"][1]["parent_id"], "parent")
        markdown = smartart_to_markdown(diagrams[0])
        self.assertIn("- Parent", markdown)
        self.assertIn("  - Child", markdown)
