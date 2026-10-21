import os
from pathlib import Path
import subprocess
import sys


def test_offline_entry_blocks_network(tmp_path):
    env = os.environ.copy()
    env["PYTHONPATH"] = str(Path(__file__).resolve().parents[1] / "src")
    source = """
import socket,sys
from free_search.__main__ import main
sys.argv=['free-search','--diagnose','--data-dir',sys.argv[1],'--model-dir',sys.argv[2]]
main()
# LanceDB starts an asyncio loop, which uses a socketpair on Windows.
import lancedb
db=lancedb.connect(sys.argv[3] + '/vectors')
table=db.create_table('test', [{'id':'one','vector':[1.0,0.0]}])
assert table.search([1.0,0.0]).limit(1).to_list()[0]['id']=='one'
try:
    socket.create_connection(('127.0.0.1',9), timeout=.1)
except PermissionError:
    print('NETWORK_BLOCKED')
else:
    raise AssertionError('Offline runtime allowed a socket connection')
"""
    result = subprocess.run([sys.executable, "-c", source, str(tmp_path / "data"), str(tmp_path / "models")],
                            capture_output=True, text=True, env=env, timeout=30)
    assert result.returncode == 0, result.stderr
    assert "NETWORK_BLOCKED" in result.stdout
