from pathlib import Path
import zipfile

import pytest

from free_search.extractors import extract, UnsupportedFormat
from free_search.models import LocalModels, ModelUnavailable


def test_chinese_encodings_and_overlap(tmp_path):
    text = "这是关于合同的正文。" * 100
    for encoding in ("utf-8-sig", "gb18030", "utf-16"):
        path = tmp_path / (encoding + ".txt")
        path.write_bytes(text.encode(encoding))
        chunks = extract(path, tmp_path / "cache")
        assert chunks[0].text == text[:420]
        assert chunks[0].text[-60:] == chunks[1].text[:60]
        assert chunks[-1].text == text[360 * (len(chunks) - 1):]


def test_code_is_read_never_executed(tmp_path):
    target = tmp_path / "executed"
    source = tmp_path / "project.py"
    source.write_text(f"open({str(target)!r}, 'w').write('oops')", encoding="utf-8")
    chunks = extract(source, tmp_path / "cache")
    assert "oops" in chunks[0].text
    assert not target.exists()


def test_docx_includes_table_and_header_text(tmp_path):
    path = tmp_path / "report.docx"
    xml = b'<w:document xmlns:w="urn:test"><w:body><w:p><w:r><w:t>Title</w:t></w:r></w:p><w:tbl><w:tr><w:tc><w:p><w:r><w:t>Budget 850</w:t></w:r></w:p></w:tc></w:tr></w:tbl></w:body></w:document>'
    header = b'<w:hdr xmlns:w="urn:test"><w:p><w:r><w:t>Department</w:t></w:r></w:p></w:hdr>'
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("word/document.xml", xml)
        archive.writestr("word/header1.xml", header)
    chunks = extract(path, tmp_path / "cache")
    assert chunks[0].text == "Title\nBudget 850"
    assert chunks[0].locator.startswith("正文")
    assert chunks[1].text == "Department"


def test_pptx_slides_sort_numerically(tmp_path):
    path = tmp_path / "slides.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        for number in (10, 2, 1):
            archive.writestr(f"ppt/slides/slide{number}.xml",
                             f'<p:sld xmlns:p="urn:p" xmlns:a="urn:a"><a:p><a:r><a:t>Slide {number}</a:t></a:r></a:p></p:sld>')
    chunks = extract(path, tmp_path / "cache")
    assert [c.text for c in chunks] == ["Slide 1", "Slide 2", "Slide 10"]
    assert chunks[-1].locator.startswith("幻灯片 3")


def test_pptx_uses_presentation_order_and_note_relationship(tmp_path):
    path = tmp_path / "reordered.pptx"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("ppt/presentation.xml",
                         '<p:presentation xmlns:p="urn:p" xmlns:r="urn:r"><p:sldIdLst><p:sldId id="256" r:id="rIdA"/><p:sldId id="257" r:id="rIdB"/></p:sldIdLst></p:presentation>')
        archive.writestr("ppt/_rels/presentation.xml.rels",
                         '<Relationships><Relationship Id="rIdA" Target="slides/slide9.xml"/><Relationship Id="rIdB" Target="slides/slide1.xml"/></Relationships>')
        archive.writestr("ppt/slides/slide9.xml", "<root><p><t>First</t></p></root>")
        archive.writestr("ppt/slides/slide1.xml", "<root><p><t>Second</t></p></root>")
        archive.writestr("ppt/slides/_rels/slide9.xml.rels",
                         '<Relationships><Relationship Id="rIdNote" Target="../notesSlides/notesSlide7.xml"/></Relationships>')
        archive.writestr("ppt/notesSlides/notesSlide7.xml", "<root><p><t>Speaker notes</t></p></root>")
    chunks = extract(path, tmp_path)
    assert [c.text for c in chunks] == ["First", "Second", "Speaker notes"]
    assert chunks[2].locator.startswith("幻灯片 1 备注")


def test_images_keep_visual_evidence_when_ocr_empty(tmp_path):
    class OCR:
        def availability(self):
            return {"ocr": True}

        def ocr(self, path):
            return ""

    path = tmp_path / "picture.png"
    path.write_bytes(b"fake image is handled by the test OCR")
    chunks = extract(path, tmp_path / "cache", OCR())
    assert len(chunks) == 1
    assert chunks[0].modality == "image"
    assert chunks[0].asset_path == str(path.resolve())


def test_image_ocr_is_chunked_and_not_truncated(tmp_path):
    class OCR:
        def availability(self):
            return {"ocr": True}

        def ocr(self, path):
            return "内容" * 500

    path = tmp_path / "picture.png"
    path.write_bytes(b"test")
    chunks = extract(path, tmp_path / "cache", OCR())
    assert chunks[0].modality == "image"
    assert len(chunks) > 2
    assert all(len(c.text) <= 420 for c in chunks)


def test_unsupported_and_missing_speech_are_explicit(tmp_path):
    with pytest.raises(UnsupportedFormat, match="内部内容"):
        extract(tmp_path / "drawing.dwg", tmp_path)
    with pytest.raises(ModelUnavailable, match="语音"):
        extract(tmp_path / "speech.wav", tmp_path)


def test_missing_models_fail_before_loading_network_libraries(tmp_path):
    models = LocalModels(tmp_path / "no-models")
    with pytest.raises(ModelUnavailable, match="不会自动联网"):
        models._load("text-embedding")
    assert models._active is None


def test_pdf_page_locators(tmp_path):
    from pypdf import PdfWriter

    path = tmp_path / "blank.pdf"
    writer = PdfWriter()
    writer.add_blank_page(width=100, height=100)
    with path.open("wb") as output:
        writer.write(output)

    class OCR:
        def availability(self):
            return {"ocr": True}

        def ocr(self, path):
            return "这是一张扫描发票"

    chunks = extract(path, tmp_path / "cache", OCR())
    assert chunks[0].modality == "image"
    assert Path(chunks[0].asset_path).exists()
    assert chunks[1].text == "这是一张扫描发票"
    assert "第 1 页" in chunks[1].locator
