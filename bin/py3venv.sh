# !/bin/bash

# if .py3venv doesn't exists, create it,
# otherwise activate the virtual environment
if [ -d .py3venv ]; then
    echo '.py3env already exists!'
else
    virtualenv .py3venv --python=python3
    source .py3venv/bin/activate
    pip install -r requirements.txt
    rm -rf liteflow.egg-info/
    deactivate
fi
