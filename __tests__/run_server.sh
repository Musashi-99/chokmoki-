#!/bin/bash
cd "$(dirname "$0")/.."
python3 __tests__/server.py ${1:-8000}

