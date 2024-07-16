#!/bin/bash
python3 -m venv ./venv
source ./venv/bin/activate
python3 -m pip install --upgrade build
python3 -m pip install --upgrade twine
#For testing
python3 -m pip install asyncio

