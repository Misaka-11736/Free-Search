# Third-party components

Original Free Search application source code is MIT licensed. The supplied binary
combination is distributed under GNU GPL version 3 because its media libraries
include GPL components. See BINARY_LICENSE.txt for the full terms. Third-party
components and model weights retain their own applicable licenses and notices.
The exact installed versions are recorded in `requirements-lock.txt`.

| Component | License / source |
| --- | --- |
| Qt / PySide6 | LGPL-3.0 / GPL-3.0 / commercial, https://doc.qt.io/qtforpython-6/licenses.html |
| Python | PSF license, https://docs.python.org/3/license.html |
| SQLite | Public domain, https://sqlite.org/copyright.html |
| LanceDB | Apache-2.0, https://github.com/lancedb/lancedb |
| PyTorch | BSD-style, https://github.com/pytorch/pytorch |
| Transformers | Apache-2.0, https://github.com/huggingface/transformers |
| RapidOCR | Apache-2.0, https://github.com/RapidAI/RapidOCR |
| faster-whisper / CTranslate2 | MIT, upstream project licenses |
| PyAV | BSD-3-Clause; bundled FFmpeg components have separate licenses |
| FFmpeg / x264 / x265 | The supplied media combination is distributed under GPLv3; https://ffmpeg.org/legal.html |
| pypdf | BSD-3-Clause, https://github.com/py-pdf/pypdf |
| pypdfium2 / PDFium | Apache-2.0 or BSD-3-Clause / BSD-style notices |
| jieba | MIT, https://github.com/fxsjy/jieba |

Model packages carry their original model cards and licenses where supplied:
multilingual-e5-small (MIT), bge-reranker-base (MIT, as declared by its downloaded model card),
Chinese-CLIP (upstream project MIT; retain the model card and upstream provenance),
Whisper/faster-whisper model (MIT).
The downloaded model manifest records repository revision and SHA256 per file.

Release packaging must preserve installed distribution license files and bundled library notices.
Qt libraries are dynamically linked in the portable directory. Users can replace them with
compatible builds; source and build instructions for this application are distributed separately.
This preview installer is unsigned; no code-signing certificate is supplied.

## Collecting notices for each release

Run the collector using the same virtual environment used to build the EXE:

```powershell
.\.venv\Scripts\python.exe scripts\collect_licenses.py --output dist\licenses
```

Copy the resulting `licenses` directory into **each** portable program distribution.
The collector preserves distribution names, versions and relative license paths, copies
model cards and license texts without copying model weights, and writes `manifest.json`
with SHA256 hashes and missing-text findings. It imports no inference models and does
not access the network. A missing-text finding requires checking the actual bundled
components; it must not be interpreted as permission to omit a required notice.

Some PyInstaller hooks already copy package licenses; this does not cover every package,
Qt module, model, or shared library. The table above is an index, not a replacement for
the complete original license and copyright texts supplied with the release.

## Binary provenance that must accompany redistribution

The installed PyAV 19.0.1 reports `LGPL version 3 or later` in
`av._core.library_meta`. Its recorded FFmpeg configuration also enables `libx264`
and `libx265`, and the portable build contains both DLLs. Those libraries have their own
licensing and corresponding-source requirements; do not infer the license of the whole
binary set from FFmpeg's single runtime label. Preserve the exact build configuration,
upstream revisions, library notices, and corresponding source/build information for the
distributed binaries. See [FFmpeg's distribution guidance](https://ffmpeg.org/legal.html).

The installed PySide6 metadata declares LGPL/GPL alternatives, while its installed
license-text files currently contain only `LicenseRef-Qt-Commercial.txt`. This is not
evidence that an open-source release may omit LGPL/GPL texts. Supply the applicable Qt
license texts and module notices, and keep Qt DLLs replaceable in the portable layout.
See [Qt for Python licensing](https://doc.qt.io/qtforpython-6/licenses.html).

Also preserve PDFium's third-party notices, ONNX Runtime notices, RapidOCR/PaddleOCR
model licenses, CTranslate2 and the binary libraries pulled in by PyAV and OpenCV.
The final installer excludes unused soundfile/sounddevice and their native libraries.
The dependency lock captures the build environment, including tools and excluded
packages; it is not a list of every file shipped in the installer and does not
by itself supply corresponding source or all license texts.

## Supplements included in this preview

`docs/third_party/` now contains upstream Qt LGPL/GPL texts, FFmpeg LGPL/GPL texts,
x264/x265 notices, supplemental package licenses and all four model license texts.
The collector copies these into each portable edition. `provenance.json` records
retrieval URLs and content hashes; entries whose revision is a branch name are not
represented as immutable upstream commits. `ffmpeg/build-config.json` preserves
the installed binary's reported configuration. Exact source archives, wheel-to-DLL
hashes, upstream build recipes and matching limitations are recorded in
[BINARY_SOURCES.md](docs/third_party/BINARY_SOURCES.md) and
`docs/third_party/source-provenance.json`. The same Release supplies the source
archives themselves, alongside this application's source and build scripts.

Unused Qt VirtualKeyboard, Qt PDF image plugin and OpenCV FFmpeg video plugin
are omitted. Application PDF rendering uses pypdfium2, and media decoding uses
PyAV. Other collected dynamic libraries retain their original license files.

The Simplified Chinese installer translation is copied from Inno Setup tag
`is-6_7_3`, `Files/Languages/Unofficial/ChineseSimplified.isl`; its translator
attribution is preserved in `packaging/ChineseSimplified.isl`.
