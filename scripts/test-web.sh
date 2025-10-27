#!/usr/bin/env sh
set -e
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
pytest -q "$@"
