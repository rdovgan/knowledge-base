#!/usr/bin/env python3
"""
MBP RAG Pipeline runner.

Usage:
  python3 run_pipeline.py           # Run pipeline (continuous)
  python3 run_pipeline.py --reset   # Reset state and start fresh
"""
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

# Allow crewai to read files outside working directory
os.environ['CREWAI_TOOLS_ALLOW_UNSAFE_PATHS'] = 'true'

sys.path.insert(0, '/home/r.dovgan/cakb')
os.chdir('/home/r.dovgan/cakb')

from pipeline.orchestrator import run_pipeline

reset = "--reset" in sys.argv
run_pipeline(reset=reset)
