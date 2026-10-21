# Native dependency sources for Windows releases

This record covers the Windows x64 dependency set inspected on 2026-10-21.
The application source is MIT licensed. The distributed program also contains
third-party libraries under their own licenses, including a GPLv3 media-library
combination. Neither the installer nor its complete contents are described as
MIT-only or LGPL-only.

The machine-readable inventory is [source-provenance.json](source-provenance.json).
The companion Release asset `FreeSearch-dependency-sources.zip` contains the
identified source archives, original build recipes and patches. Its SHA256 file
lets recipients verify the downloaded asset. Original license texts accompany
the program in `licenses/`; source archive licenses remain intact as well.

## PyAV and FFmpeg: verified binary and source chain

The inspected Python wheel is `av-19.0.1-cp312-abi3-win_amd64.whl`, from
[PyPI's av 19.0.1 release](https://pypi.org/project/av/19.0.1/).
Its SHA256 is
`906fc3db09288319a75ea23ffefb59961c7dbe0d1c074601507a89de7d8593d8`.
All 23 DLLs under `av.libs` in the inspected portable editions match that wheel
byte for byte. Individual hashes are recorded in the inventory.

[PyAV v19.0.1](https://github.com/PyAV-Org/PyAV/tree/52e6691c8221a53ac1f1bf111f282cefa7d568e1)
locks its vendor download to
[pyav-ffmpeg 9.0.2-1](https://github.com/PyAV-Org/pyav-ffmpeg/tree/bac889417e26be29615cb6a3f38318151fed55cd).
The vendor recipe supplies FFmpeg 9.0.2 and pins source hashes for its additional
codecs. The runtime reports FFmpeg 9.0.2 and library major versions 61/63/63 for
avutil/avcodec/avformat, consistent with that recipe.

The upstream recipe's
[FFmpeg patch](https://github.com/PyAV-Org/pyav-ffmpeg/blob/bac889417e26be29615cb6a3f38318151fed55cd/patches/ffmpeg.patch)
moves `libx264` and `libx265` from `EXTERNAL_LIBRARY_GPL_LIST` into
`EXTERNAL_LIBRARY_VERSION3_LIST`. This explains why the DLL reports
`LGPL version 3 or later` despite enabling and linking both GPL codecs. The
configuration patch does not change those libraries' original licenses. The
release therefore identifies the media combination as GPLv3 and supplies its
corresponding source material, including that patch.

The sources include:

| Component | Identified version / source | Original license material |
| --- | --- | --- |
| PyAV | 19.0.1, commit `52e6691c8221a53ac1f1bf111f282cefa7d568e1` | BSD-3-Clause |
| FFmpeg | 9.0.2 plus the vendor patch | LGPL/GPL texts; media combination distributed as GPLv3 |
| x264 | `b35605ace3ddf7c1a5d67a2eb553f034aef41d55` | GPL-2.0-or-later |
| x265 | 4.3; runtime string `4.3+1-e9b8812` | GPL-2.0-or-later |
| lamer | 3.101.0 | LGPL-2.1-or-later |
| Opus | 1.6.1 | BSD-style `COPYING` |
| dav1d | 1.5.4 | BSD-2-Clause |
| SVT-AV1 | 4.2.0 | BSD-3-Clause-Clear, BSD-2-Clause and patent text; retain per-file terms |
| libvpx | 1.17.0 | BSD-3-Clause and `PATENTS` |
| libpng | 1.6.58 | libpng license |
| libwebp / libsharpyuv | 1.6.0 | BSD-3-Clause and `PATENTS` |
| libvmaf | 3.2.1 | BSD-2-Clause-Patent |
| Intel libvpl | 2.16.0 | MIT |
| NVIDIA codec headers | 13.0.19.0 | License/copyright notices in the headers |
| AMD AMF headers | 1.5.2 | License/copyright notices in the headers |
| libiconv | MSYS2 1.19-1 | LGPL-2.1-or-later for the library; retain source documentation terms |
| zlib | MSYS2 1.3.2-2 | Zlib |
| libgcc / libstdc++ | MSYS2 GCC 16.1.0-5 | GPL-3.0-or-later WITH GCC-exception-3.1 |
| winpthreads | Code matches MSYS2 14.0.0.r92 and r98 packages; r98 source supplied | MIT and BSD-3-Clause-Clear |

The original MSYS2 libiconv DLL and the wheel DLL have identical PE section
contents. The matched zlib and winpthreads packages have identical code and data
sections. GCC runtime code sections match GCC 16.1.0-5; wheel repair changes
dependency names and associated data. Full MSYS2 source packages include their
`PKGBUILD`, patches and upstream source, rather than just a link to current Git
HEAD. The winpthreads r92 and r98 binary code/data are identical, so those bytes
alone do not uniquely distinguish the two package revisions. This ambiguity is
recorded instead of assigning an unsupported unique package origin.

Older official Windows CPython 3.12 wheels were also checked: PyAV 15.1.0 and
16.0.1 both enable x264/x265 and use the same LGPL runtime-label pattern. PyAV
12.3.0 also includes those codecs and explicitly enables GPL. Those wheels were
not used to replace the selected 19.0.1 dependency.

## Rebuilding or replacing the media libraries

1. Extract `pyav-ffmpeg-bac889417e26.tar.gz` and the dependency sources from the
   companion asset. The recipe's `scripts/pkg.py` gives every pinned archive
   URL and SHA256; `patches/` contains the original source modifications.
2. Follow `.github/workflows/build-ffmpeg.yml` for Windows x86_64. It uses the
   MSYS2 MINGW64 GCC toolchain, `base-devel`, `pkgconf`, NASM, Python,
   CMake/Meson/Ninja, and `scripts/build-ffmpeg.py C:\cibw\vendor`.
   Source-package builds use the contained MSYS2 `PKGBUILD` files. Windows 11's
   `tar` or MSYS2 `tar` can extract the supplied `.src.tar.zst` files.
3. To make a new correctly labelled GPL build, remove the vendor's
   `patches/ffmpeg.patch`, keep x264/x265 enabled, and explicitly add
   `--enable-gpl` alongside `--enable-version3`. This produces a different
   binary from the inspected wheel; retain its own source hashes and config.
4. Extract the PyAV 19.0.1 source and follow its Windows build instructions in
   `README.md` and `.github/workflows/tests.yml`. Its wheel build uses the
   vendor headers/libraries and `delvewheel repair` to package DLLs.
5. Rebuild Free Search with the resulting wheel using `scripts/build.ps1`.
   Use a separate environment for modified libraries. Run the project tests,
   speech/video extraction checks and installed-EXE checks before replacing a
   distributed edition. Keep the DLLs as separate replaceable files.

The supplied original recipe documents the inspected build; these records do
not claim a byte-for-byte reproducible rebuild was performed. Normal compiler,
SDK and build-tool installation is still required. No signing or checksum
enforcement in the application prevents users from replacing compatible DLLs.

## Qt and PySide6

The Qt/PySide6 release is 6.12.0. The companion sources include the official
`pyside-setup-everywhere-src-6.12.0` archive and these official Qt modules:

- `qtbase`: Core, Gui, Widgets, Network, OpenGL and platform plugins.
- `qtdeclarative`: QML and Quick DLLs retained by the packaged runtime.
- `qtsvg`: SVG rendering and icon plugins.
- `qtimageformats`: optional image-format plugins.
- `qtshadertools`: build/source support for Qt Quick.

The archives come from the
[official Qt 6.12.0 source directory](https://download.qt.io/official_releases/qt/6.12/6.12.0/submodules/)
and the
[official PySide6 source directory](https://download.qt.io/official_releases/QtForPython/pyside6/PySide6-6.12.0-src/).
The inventory records the downloaded byte counts and SHA256 hashes. LGPLv3/GPL
texts and module third-party notices must accompany the binary distribution;
the commercial-only text present in the installed wheel is insufficient by
itself.

Qt DLLs stay outside the EXE in `_internal/PySide6`. Rebuild Qt 6.12.0 following
the archive's Windows build documentation, then rebuild PySide6/Shiboken from
the matching `pyside-setup` source if necessary. Replace the matching Qt/PySide6
DLL set and plugins with interface-compatible builds, or rebuild the
application from its supplied source. Use the same architecture and compatible
MSVC runtime. See
[Qt for Python source builds](https://doc.qt.io/qtforpython-6/building_from_source/index.html).

Qt Virtual Keyboard is GPLv3-only under its open-source option and is unused by
the application. Its plugin and DLL are excluded from the release. Qt PDF's
actual DLL version is 6.140.0 rather than 6.12.0; its unused `qpdf` image plugin
and DLL are also excluded. The application renders PDFs with pypdfium2. Retaining
either excluded component in a future build requires adding its matching
sources and notices to this inventory.

## PDFium, OCR and the other native packages

- pypdfium2 5.14.0 ships PDFium `156.0.8076.0` from the
  [pdfium-binaries chromium/8076 build](https://github.com/bblanchon/pdfium-binaries/releases/tag/chromium%2F8076).
  Its installed `BUILD_LICENSES` includes PDFium, FreeType, ICU, libjpeg-turbo,
  OpenJPEG, libpng, LCMS, AGG, Abseil and other notices. Preserve that directory
  unchanged. The permissive PDFium license requires these notices, rather than
  applying Qt's license to PDFium.
- RapidOCR 1.4.4 packages the PP-OCRv4 detector/recognizer and PP-OCRv2 classifier
  ONNX weights. Their file hashes and wheel origin are listed in the inventory.
  Retain RapidOCR and PaddleOCR Apache-2.0 notices. The application uses those
  installed files without converting or changing the weights.
- ONNX Runtime 1.31.0 includes `LICENSE` and `ThirdPartyNotices.txt`; OpenCV
  5.0.0.93 includes `LICENSE.txt` and `LICENSE-3RD-PARTY.txt`. The unused OpenCV
  FFmpeg video plugin is excluded; media decoding uses the separately documented
  PyAV DLL set.
- CTranslate2 4.8.3 has its MIT notice. Python/PyTorch and other package notices
  are collected from the build environment by `scripts/collect_licenses.py`.
  The dependency lock and collected `licenses/manifest.json` remain the complete
  installed-version and notice inventory.
- SoundFile/libsndfile and SoundDevice/PortAudio are unused by the application
  and excluded from the installer, including the unused ASIO variants. Audio
  decoding and speech input files use the documented PyAV media libraries.

## Producing the companion asset

Using the checked source cache, run:

```powershell
.\.venv\Scripts\python.exe scripts\package_dependency_sources.py
```

For a new checkout, add `--download` to obtain the pinned archives from the URLs
in the inventory. The script checks every archive's size and SHA256 before
packaging, preserves the original archives unchanged, and emits the ZIP and a
`.sha256` sidecar under `dist/installer-release/`. A checksum mismatch stops
packaging. The source asset and the complete application source/build scripts
must remain available with the corresponding binary Release.

This document records technical provenance and packaging actions. It is not a
legal certification, and does not replace the original license terms.
