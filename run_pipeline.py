import sys
import os
from pathlib import Path

# Load .env
env_file = Path('/home/r.dovgan/cakb/.env')
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith('#') and '=' in line:
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

# Дозволяємо crewai читати файли поза робочою директорією
os.environ['CREWAI_TOOLS_ALLOW_UNSAFE_PATHS'] = 'true'

sys.path.insert(0, '/home/r.dovgan/cakb')
os.chdir('/home/r.dovgan/cakb')

from pipeline.orchestrator import run_pipeline

module_arg = sys.argv[1] if len(sys.argv) > 1 else None
run_pipeline(single_module=module_arg)
