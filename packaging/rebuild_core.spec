# Recompile the existing dependency closure without importing model packages.
# No dependency, model or runtime hook changed in this source-only revision.
import ast
from pathlib import Path

root = Path(SPECPATH).parent
analysis = ast.literal_eval((root / 'build/FreeSearch-offline/Analysis-00.toc').read_text(encoding='utf-8'))
assert analysis[12].startswith('3.12.14 ')
assert all(any(name == target for name, _, _ in analysis[14])
           for target in ('free_search.engine', 'free_search.ui', 'free_search.__main__'))
pyz = PYZ(analysis[14])
exe = EXE(pyz, analysis[13], [], exclude_binaries=True,
          name='FreeSearch-offline', debug=False, bootloader_ignore_signals=False,
          strip=False, upx=True, console=False, disable_windowed_traceback=False,
          argv_emulation=False, target_arch=None, codesign_identity=None,
          entitlements_file=None)
