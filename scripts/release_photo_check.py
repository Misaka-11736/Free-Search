"""Verify the shipped installer on a fresh Windows Server GitHub runner."""
from pathlib import Path
import hashlib
import json
import os
import platform
import shutil
import subprocess
import time

ROOT = Path(os.environ["RUNNER_TEMP"]) / "FreeSearchReleaseCheck"
ROOT.mkdir()
REPORTS = ROOT / "reports"
REPORTS.mkdir()
INSTALL = ROOT / "program"
USER = ROOT / "user"
DATA = USER / "FreeSearch/data"
FIXTURES = ROOT / "fixtures"
FIXTURES.mkdir()
MANIFEST = json.loads(Path("release-build-reports/manifest.json").read_text())
BASE = f"repos/{os.environ['GITHUB_REPOSITORY']}"
RULES = [f"FreeSearch-ReleaseCheck-{e}" for e in ("offline", "api")]
report = {"environment": platform.platform(), "fresh_github_hosted_vm": True,
          "windows_11": False, "personal_files_used": False, "checks": []}


def save():
    (REPORTS / "verification.json").write_text(json.dumps(report, indent=2), encoding="utf8")


def powershell(code):
    return subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-Command", code],
                          capture_output=True, text=True, check=True)


assets = json.loads(subprocess.run(
    ["gh", "api", f"{BASE}/releases/{MANIFEST['release_id']}/assets?per_page=100"],
    capture_output=True, check=True).stdout)
for expected in MANIFEST["expected"]:
    if not expected["name"].endswith((".exe", ".bin")):
        continue
    asset = next(a for a in assets if a["name"] == expected["name"])
    path = ROOT / asset["name"]
    with path.open("wb") as stream:
        subprocess.run(["gh", "api", f"{BASE}/releases/assets/{asset['id']}",
                        "-H", "Accept: application/octet-stream"], check=True, stdout=stream)
    with path.open("rb") as stream:
        assert hashlib.file_digest(stream, "sha256").hexdigest() == expected["sha256"]
    assert path.stat().st_size == expected["bytes"]
report["installer_hashes_verified"] = True
save()
setup = ROOT / "FreeSearch-Setup-0.1.0-preview.2.exe"
started = time.monotonic()
installed = subprocess.run([str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/SP-",
                            "/NOICONS", "/TASKS=", f"/DIR={INSTALL}", f"/LOG={REPORTS / 'install.log'}"], timeout=900)
report.update(install_exit_code=installed.returncode, install_seconds=time.monotonic() - started)
save()
assert installed.returncode == 0 and (INSTALL / "installed.json").is_file()
assert json.loads((INSTALL / "installed.json").read_text())["version"] == "0.1.0-preview.2"
(FIXTURES / "cooling.txt").write_text(
    "电池散热设计。液冷板和冷却液带走电池的热量，避免电池过热。\n"
    "Battery thermal management uses liquid cooling plates and coolant to transfer heat.", encoding="utf8")
(FIXTURES / "astronomy.txt").write_text("星空观测和行星轨道。 Astronomy studies stars and planetary orbits.", encoding="utf8")
shutil.copyfile("packaging/transfer-fixtures/query.wav", FIXTURES / "query.wav")
shutil.copyfile("packaging/transfer-fixtures/visual.png", FIXTURES / "visual.png")
app_env = os.environ.copy()
for variable in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "GH_TOKEN", "GITHUB_TOKEN"):
    app_env.pop(variable, None)
app_env["PATH"] = str(Path(os.environ["WINDIR"]) / "System32")
app_env["LOCALAPPDATA"] = str(USER)
app_env["QT_QPA_PLATFORM"] = "offscreen"
try:
    powershell("Set-NetFirewallProfile -Profile Domain,Private,Public -Enabled True -ErrorAction Stop")
    profiles = json.loads(powershell("Get-NetFirewallProfile | Select-Object Name,Enabled | ConvertTo-Json -Compress").stdout)
    assert all(profile["Enabled"] in (True, 1, "True") for profile in profiles)
    report["firewall_profiles_enabled"] = profiles
    for edition, rule in zip(("offline", "api"), RULES):
        executable = INSTALL / f"FreeSearch-{edition}.exe"
        powershell(f"New-NetFirewallRule -DisplayName '{rule}' -Direction Outbound -Program '{executable}' "
                   "-Action Block -Profile Any -RemoteAddress '0.0.0.0-126.255.255.255',"
                   "'128.0.0.0-255.255.255.255','::2-ffff:ffff:ffff:ffff:ffff:ffff:ffff:ffff' "
                   "-ErrorAction Stop | Out-Null")
    report["os_firewall_blocks_both_executables"] = True
    save()
    image_output = REPORTS / "images-first.json"
    result = subprocess.run([str(INSTALL / "FreeSearch-offline.exe"), "--index", str(FIXTURES), "--images-only",
                             "--query", "project schedule weekly meeting", "--mode", "bm25", "--diagnose",
                             "--output", str(image_output)], env=app_env, cwd=INSTALL, timeout=600)
    images = json.loads(image_output.read_text(encoding="utf8"))
    assert result.returncode == 0 and images["index"]["processed"] == 1 and images["index"]["deferred"] == 3
    assert images["index"]["failed"] == 0 and images["diagnostics"]["files"] == 1
    assert Path(images["results"][0]["path"]).name == "visual.png"
    report["image_stage_search_before_documents"] = True
    report["image_stage"] = images["index"]
    save()
    for edition in ("offline", "api"):
        output = REPORTS / f"{edition}.json"
        executable = INSTALL / f"FreeSearch-{edition}.exe"
        started = time.monotonic()
        result = subprocess.run([str(executable), "--index", str(FIXTURES), "--query", "电池如何降低温度",
                                 "--transcribe", str(FIXTURES / "query.wav"), "--diagnose", "--output", str(output)],
                                env=app_env, cwd=INSTALL, timeout=900)
        details = json.loads(output.read_text(encoding="utf8")) if output.exists() else {}
        index = details.get("index", {})
        passed = (result.returncode == 0 and index.get("failed") == 0
                  and Path(details.get("results", [{}])[0].get("path", "")).name == "cooling.txt"
                  and "battery" in str(details.get("transcription", [])).lower()
                  and details.get("diagnostics", {}).get("edition") == edition
                  and (DATA / "catalog.sqlite").is_file() and not (INSTALL / "runtime-data").exists())
        passed = passed and (index.get("processed") == 3 and index.get("unchanged") == 1 if edition == "offline"
                             else index.get("processed") == 0 and index.get("unchanged") == 4)
        report["checks"].append({"edition": edition, "passed": passed, "exit_code": result.returncode,
                                  "seconds": time.monotonic() - started, "index": index})
        save()
        print(json.dumps(report["checks"][-1]), flush=True)
        assert passed, f"{edition} inference failed"
    ocr_output = REPORTS / "ocr.json"
    result = subprocess.run([str(INSTALL / "FreeSearch-offline.exe"), "--query", "project schedule weekly meeting",
                             "--mode", "bm25", "--output", str(ocr_output)], env=app_env, cwd=INSTALL, timeout=180)
    details = json.loads(ocr_output.read_text(encoding="utf8"))
    report["ocr_search_passed"] = (result.returncode == 0
        and Path(details.get("results", [{}])[0].get("path", "")).name == "visual.png")
    save()
    assert report["ocr_search_passed"]
    sentinel = DATA / "keep-data.txt"
    sentinel.write_text("Preserve application index on uninstall", encoding="utf8")
    removed = subprocess.run([str(INSTALL / "unins000.exe"), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART",
                              f"/LOG={REPORTS / 'uninstall.log'}"], timeout=180)
    for _ in range(30):
        if not (INSTALL / "FreeSearch-offline.exe").exists():
            break
        time.sleep(.5)
    report.update(uninstall_exit_code=removed.returncode,
                  program_removed=not (INSTALL / "FreeSearch-offline.exe").exists(),
                  user_index_preserved=(DATA / "catalog.sqlite").is_file() and sentinel.is_file())
    report["passed"] = (removed.returncode == 0 and report["program_removed"] and report["user_index_preserved"])
    save()
    assert report["passed"]
finally:
    for rule in RULES:
        powershell(f"Get-NetFirewallRule -DisplayName '{rule}' -ErrorAction SilentlyContinue | Remove-NetFirewallRule")
    save()
Path(os.environ["GITHUB_STEP_SUMMARY"]).write_text(
    "Fresh Windows Server hosted VM, synthetic fixtures only. OS firewall blocked outbound traffic for both executables.\n\n"
    + "```json\n" + json.dumps(report, indent=2) + "\n```\n", encoding="utf8")
