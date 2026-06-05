from __future__ import annotations

import subprocess
import sys
import zipfile
from pathlib import Path

import yaml


def test_parse_docx_extracts_images_and_manifest(tmp_path: Path):
    docx = tmp_path / "requirements.docx"
    with zipfile.ZipFile(docx, "w") as zf:
        zf.writestr(
            "word/document.xml",
            """<?xml version="1.0" encoding="UTF-8"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
  xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
  xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">
  <w:body>
    <w:p>
      <w:r><w:t>Process image follows</w:t></w:r>
      <w:r><w:drawing><a:blip r:embed="rId5"/></w:drawing></w:r>
    </w:p>
  </w:body>
</w:document>
""",
        )
        zf.writestr(
            "word/_rels/document.xml.rels",
            """<?xml version="1.0" encoding="UTF-8"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
  <Relationship Id="rId5" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/image1.png"/>
</Relationships>
""",
        )
        zf.writestr("word/media/image1.png", b"\x89PNG\r\n\x1a\n")

    result = subprocess.run(
        [sys.executable, "scripts/parse_docx.py", "--input", str(docx), "--workspace", str(tmp_path / "workspace")],
        text=True,
        capture_output=True,
    )

    assert result.returncode == 0, result.stdout + result.stderr
    manifest_path = tmp_path / "workspace" / "parsed" / "image-manifest.yaml"
    manifest = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))["image_manifest"]
    assert manifest[0]["image_id"] == "IMG-001"
    assert manifest[0]["near_block_id"] == "B-0001"
    assert manifest[0]["filename"] == "parsed/images/IMG-001.png"
    assert (tmp_path / "workspace" / "parsed" / "images" / "IMG-001.png").exists()
    ir = yaml.safe_load((tmp_path / "workspace" / "parsed" / "document-ir.yaml").read_text(encoding="utf-8"))
    assert ir["document_ir"]["blocks"][0]["image_ids"] == ["IMG-001"]
