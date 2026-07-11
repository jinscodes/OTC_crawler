#!/usr/bin/env bash

MIN_MAJOR=3
MIN_MINOR=10
VENV_DIR=".venv"
REQ_FILE="academic_torrent/requirements.txt"

# --- pick a python interpreter that is >= 3.10 --------------------------------
choose_python() {
  for cand in python3.12 python3.11 python3.10 python3; do
    if command -v "$cand" >/dev/null 2>&1; then
      if "$cand" -c "import sys; sys.exit(0 if sys.version_info[:2] >= ($MIN_MAJOR,$MIN_MINOR) else 1)"; then
        echo "$cand"; return 0
      fi
    fi
  done
  return 1
}

echo "==> Looking for Python >= ${MIN_MAJOR}.${MIN_MINOR} ..."
PY="$(choose_python || true)"

# --- install Python if none found (Ubuntu/Debian only) ------------------------
if [ -z "${PY:-}" ]; then
  if command -v apt-get >/dev/null 2>&1; then
    echo "==> Not found. Installing Python via apt (uses sudo) ..."
    sudo apt-get update -y
    sudo apt-get install -y python3 python3-venv python3-pip
    PY="$(choose_python || true)"

    # Still too old (e.g. Ubuntu 20.04 ships 3.8)? Use the deadsnakes PPA for 3.11.
    if [ -z "${PY:-}" ]; then
      echo "==> Distro Python too old; installing python3.11 from deadsnakes ..."
      sudo apt-get install -y software-properties-common
      sudo add-apt-repository -y ppa:deadsnakes/ppa
      sudo apt-get update -y
      sudo apt-get install -y python3.11 python3.11-venv
      PY="python3.11"
    fi
  else
    echo "ERROR: No Python >= ${MIN_MAJOR}.${MIN_MINOR} and apt-get is unavailable." >&2
    echo "       Install Python 3.10+ manually (macOS: 'brew install python@3.11')." >&2
    exit 1
  fi
fi

echo "==> Using $PY ($($PY --version 2>&1))"

# --- ensure the venv module is present (Ubuntu splits it into its own package) -
if ! "$PY" -c "import venv" >/dev/null 2>&1; then
  echo "==> Installing venv module ..."
  sudo apt-get install -y "${PY}-venv" 2>/dev/null || sudo apt-get install -y python3-venv
fi

# --- create the virtual environment ------------------------------------------
echo "==> Creating virtual environment at ./$VENV_DIR ..."
"$PY" -m venv "$VENV_DIR"

# --- install packages ---------------------------------------------------------
echo "==> Upgrading pip and installing packages from $REQ_FILE ..."
"$VENV_DIR/bin/python" -m pip install --upgrade pip
"$VENV_DIR/bin/python" -m pip install -r "$REQ_FILE"

echo
echo "==> Done."
echo "    Activate:  source $VENV_DIR/bin/activate"
echo "    Check:     python academic_torrent/step0_config.py"
echo "    Run:       python academic_torrent/crawling_reddit.py"
