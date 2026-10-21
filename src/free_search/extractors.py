"""Read source files without executing code, macros, or embedded programs."""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
import posixpath
import re
import xml.etree.ElementTree as ET
import zipfile


TEXT_EXTENSIONS = {
    ".txt", ".md", ".rst", ".csv", ".tsv", ".json", ".jsonl", ".xml", ".yaml", ".yml",
    ".toml", ".ini", ".cfg", ".log", ".tex", ".bib", ".html", ".htm", ".css",
    ".py", ".pyi", ".ipynb", ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte",
    ".c", ".h", ".cc", ".cpp", ".hpp", ".cs", ".java", ".kt", ".kts", ".go", ".rs",
    ".rb", ".php", ".swift", ".m", ".mm", ".r", ".R", ".sql", ".sh", ".ps1",
    ".bat", ".cmd", ".cmake", ".gradle", ".pro", ".sln", ".vcxproj", ".csproj",
}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".tif", ".tiff", ".webp"}
AUDIO_EXTENSIONS = {".wav", ".mp3", ".m4a", ".aac", ".flac", ".ogg", ".wma"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".mov", ".avi", ".webm", ".wmv", ".m4v"}
SUPPORTED_EXTENSIONS = TEXT_EXTENSIONS | IMAGE_EXTENSIONS | AUDIO_EXTENSIONS | VIDEO_EXTENSIONS | {
    ".pdf", ".docx", ".pptx",
}


@dataclass
class Chunk:
    text: str
    locator: str = ""
    modality: str = "text"
    asset_path: str | None = None


class UnsupportedFormat(ValueError):
    pass


def _parts(text: str, locator: str, modality: str = "text", asset_path=None) -> list[Chunk]:
    """Short overlapping passages fit the Chinese E5 token budget."""
    text = text.strip()
    if not text:
        return []
    return [Chunk(text[start:start + 420], f"{locator} · 段 {start // 360 + 1}", modality, asset_path)
            for start in range(0, len(text), 360) if text[start:start + 420].strip()]


def _cache(path: Path, cache_dir: Path) -> Path:
    stat = path.stat()
    key = f"{path.resolve()}\0{stat.st_mtime_ns}\0{stat.st_size}"
    directory = cache_dir / hashlib.sha256(key.encode("utf-8")).hexdigest()
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _image(path: Path, locator: str, models) -> list[Chunk]:
    # Visual evidence remains searchable even when OCR finds no characters.
    text = models.ocr(path) if models is not None and models.availability().get("ocr") else ""
    chunks = [Chunk("", locator, "image", str(path.resolve()))]
    chunks.extend(_parts(text, locator + " OCR", "ocr"))
    return chunks


def _read_text(path):
    raw = path.read_bytes()
    if raw.startswith((b"\xff\xfe", b"\xfe\xff")):
        return raw.decode("utf-16")
    if b"\0" in raw[:4096]:
        raise ValueError("文件含二进制内容，无法作为文本读取")
    for encoding in ("utf-8-sig", "gb18030"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("无法识别文本编码（支持 UTF-8、UTF-16 BOM、GB18030）")


def _xml_text(xml: bytes) -> str:
    root = ET.fromstring(xml)
    lines = []
    for paragraph in root.iter():
        if paragraph.tag.rsplit("}", 1)[-1] == "p":
            lines.append("".join(node.text or "" for node in paragraph.iter()
                                 if node.tag.rsplit("}", 1)[-1] == "t"))
    return "\n".join(lines)


def _relationships(archive, part):
    folder, filename = posixpath.split(part)
    rels_name = posixpath.join(folder, "_rels", filename + ".rels")
    if rels_name not in archive.namelist():
        return {}
    relationships = {}
    for node in ET.fromstring(archive.read(rels_name)):
        if node.get("TargetMode") == "External":
            continue
        target = node.get("Target", "")
        relationships[node.get("Id")] = posixpath.normpath(
            target.lstrip("/") if target.startswith("/") else posixpath.join(folder, target))
    return relationships


def _office(path, cache_dir, models):
    chunks = []
    with zipfile.ZipFile(path) as archive:
        names = archive.namelist()
        if path.suffix.lower() == ".docx":
            xmls = [n for n in names if n == "word/document.xml"
                    or re.fullmatch(r"word/(header\d+|footer\d+|footnotes|endnotes)\.xml", n)]
            xmls.sort(key=lambda n: (n != "word/document.xml", n))
            labels = {n: ("正文" if n == "word/document.xml" else n.split("/")[-1]) for n in xmls}
        else:
            # slide file numbers do not necessarily equal the visible slide order.
            if "ppt/presentation.xml" in names:
                relationships = _relationships(archive, "ppt/presentation.xml")
                root = ET.fromstring(archive.read("ppt/presentation.xml"))
                xmls = []
                for node in root.iter():
                    if node.tag.rsplit("}", 1)[-1] == "sldId":
                        rel_id = next((v for k, v in node.attrib.items()
                                       if k.rsplit("}", 1)[-1] == "id" and "}" in k), None)
                        if rel_id in relationships:
                            xmls.append(relationships[rel_id])
            else:
                xmls = [n for n in names if re.fullmatch(r"ppt/slides/slide\d+\.xml", n)]
                xmls.sort(key=lambda n: int(re.search(r"slide(\d+)", n).group(1)))
            labels = {n: f"幻灯片 {index}" for index, n in enumerate(xmls, 1)}
            for slide in list(xmls):
                for note in _relationships(archive, slide).values():
                    if "/notesSlides/" in note and note in names:
                        xmls.append(note)
                        labels[note] = labels[slide] + " 备注"
        for name in xmls:
            chunks.extend(_parts(_xml_text(archive.read(name)), labels[name]))
        if models is not None:
            directory = _cache(path, cache_dir)
            for index, name in enumerate(names):
                if "/media/" in name and Path(name).suffix.lower() in IMAGE_EXTENSIONS:
                    target = directory / f"media-{index}{Path(name).suffix.lower()}"
                    target.write_bytes(archive.read(name))
                    chunks.extend(_image(target, f"内嵌图片 {name}", models))
    return chunks


def _pdf(path, cache_dir, models):
    from pypdf import PdfReader

    reader = PdfReader(path)
    if reader.is_encrypted and not reader.decrypt(""):
        raise ValueError("PDF 已加密，需要先解密后索引")
    chunks = []
    rendered = None
    try:
        if models is not None:
            import pypdfium2 as pdfium

            rendered = pdfium.PdfDocument(path)
            directory = _cache(path, cache_dir)
        for page_number, page in enumerate(reader.pages, 1):
            label = f"第 {page_number} 页"
            text = page.extract_text() or ""
            chunks.extend(_parts(text, label))
            if rendered is not None:
                pdf_page = rendered[page_number - 1]
                bitmap = pdf_page.render(scale=1.5)
                image = bitmap.to_pil()
                target = directory / f"page-{page_number}.png"
                image.save(target)
                image.close()
                bitmap.close()
                pdf_page.close()
                chunks.append(Chunk("", label, "image", str(target)))
                if len(text.strip()) < 20 and models.availability().get("ocr"):
                    chunks.extend(_parts(models.ocr(target), label + " OCR", "ocr"))
    finally:
        if rendered is not None:
            rendered.close()
    return chunks


def _speech(path, models):
    if models is None or not models.availability().get("speech"):
        from .models import ModelUnavailable

        raise ModelUnavailable("缺少本地语音模型 speech，无法读取讲话内容。")
    return [chunk for segment in models.transcribe(path)
            for chunk in _parts(segment["text"], f"时间 {segment['start']:.2f}–{segment['end']:.2f} 秒",
                                "speech")]


def _video(path, cache_dir, models):
    import av

    chunks = []
    directory = _cache(path, cache_dir)
    with av.open(str(path)) as container:
        has_audio = bool(container.streams.audio)
        if container.streams.video:
            # Sample from decoded frames; no external executable or shell command.
            # Sparse sampling is explicitly documented; it cannot guarantee every short event.
            next_time = 0.0
            for frame in container.decode(video=0):
                timestamp = float(frame.time or 0.0)
                if timestamp < next_time:
                    continue
                target = directory / f"frame-{timestamp:.3f}.jpg"
                image = frame.to_image()
                image.thumbnail((1280, 1280))
                image.save(target, quality=85)
                image.close()
                chunks.extend(_image(target, f"时间 {timestamp:.2f} 秒", models))
                next_time = timestamp + 10.0
    if has_audio:
        chunks.extend(_speech(path, models))
    return chunks


def extract(path: Path, cache_dir: Path, models=None) -> list[Chunk]:
    path = Path(path)
    cache_dir = Path(cache_dir)
    suffix = path.suffix.lower()
    if suffix in TEXT_EXTENSIONS or path.name.lower() in {"makefile", "dockerfile", "license"}:
        return _parts(_read_text(path), "文本")
    if suffix in IMAGE_EXTENSIONS:
        return _image(path, "图片", models)
    if suffix in {".docx", ".pptx"}:
        return _office(path, cache_dir, models)
    if suffix == ".pdf":
        return _pdf(path, cache_dir, models)
    if suffix in AUDIO_EXTENSIONS:
        return _speech(path, models)
    if suffix in VIDEO_EXTENSIONS:
        return _video(path, cache_dir, models)
    raise UnsupportedFormat(f"尚不支持读取 {suffix or '无扩展名'} 文件的内部内容")
