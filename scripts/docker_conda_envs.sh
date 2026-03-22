#!/usr/bin/env bash
# Purpose: Create all RoboTwin-related conda envs inside the thesis-draft image.
# Dependencies: conda (miniforge), bash, sed, repo at ROBOTWIN_ROOT.
# Usage: called from Dockerfile; not intended for host use unless paths match.
#
# @input: ROBOTWIN_ROOT must point to .../third_party/RoboTwin
# @output: exit 0 if all requested envs were created; non-zero on first failure
# @scenario: multi-environment Docker image for simulation, ACT, VLA train/eval, RLDS

set -euo pipefail

RW="${ROBOTWIN_ROOT:?ROBOTWIN_ROOT is required}"
INSTALL_RLDS="${INSTALL_RLDS:-1}"
INSTALL_DEXVLA="${INSTALL_DEXVLA:-1}"
INSTALL_EVAL_ROBOTWIN="${INSTALL_EVAL_ROBOTWIN:-1}"

strip_tuna_mirrors() {
  local src="$1"
  local dst="$2"
  sed '/mirrors\.tuna\.tsinghua\.edu\.cn/d' "$src" >"$dst"
}

log() { echo "[docker_conda_envs] $*"; }

if ! command -v conda >/dev/null 2>&1; then
  echo "[docker_conda_envs] ERROR: conda not in PATH" >&2
  exit 1
fi

# --- thesis: RoboTwin script/sim (Python 3.11, pip) ---
log "Creating env: thesis (python 3.11 + script/requirements.txt)"
conda create -n thesis python="${THESIS_PYTHON_VERSION:-3.11}" -y
conda run -n thesis pip install --no-cache-dir -r "${RW}/script/requirements.txt"

# --- robotwin-act: full conda explicit export (conda + pip-installed pkgs as pypi_0 pins) ---
# Source: policy/ACT/requirements.txt (header documents: conda create --name <env> --file <this file>).
# Channels: export has no channel list; match typical ACT stack (pytorch + nvidia + conda-forge).
# policy/ACT/conda_env.yaml is an older minimal sketch, not the full lock.
log "Creating env: robotwin-act (conda create --file policy/ACT/requirements.txt)"
conda create -n robotwin-act \
  --file "${RW}/policy/ACT/requirements.txt" \
  -c pytorch -c nvidia -c conda-forge -c defaults

if [[ "${INSTALL_RLDS}" == "1" ]]; then
  log "Creating env: rlds_env (openvla-oft RLDS builder, Ubuntu)"
  conda env create -f "${RW}/policy/openvla-oft/rlds_dataset_builder/environment_ubuntu.yml"
else
  log "Skipping env: rlds_env (INSTALL_RLDS=${INSTALL_RLDS})"
fi

if [[ "${INSTALL_DEXVLA}" == "1" ]]; then
  log "Creating env: dexvla-robo (TinyVLA train stack)"
  conda env create -f "${RW}/policy/TinyVLA/Train_Tiny_DexVLA_train.yml"
else
  log "Skipping env: dexvla-robo (INSTALL_DEXVLA=${INSTALL_DEXVLA})"
fi

if [[ "${INSTALL_EVAL_ROBOTWIN}" == "1" ]]; then
  log "Creating env: RoboTwin (TinyVLA eval lockfile; channels without Tsinghua mirrors)"
  strip_tuna_mirrors "${RW}/policy/TinyVLA/Eval_Tiny_DexVLA_environment.yml" /tmp/RoboTwin_eval_env.yml
  conda env create -f /tmp/RoboTwin_eval_env.yml
else
  log "Skipping env: RoboTwin (INSTALL_EVAL_ROBOTWIN=${INSTALL_EVAL_ROBOTWIN})"
fi

log "Cleaning conda package cache"
conda clean -afy

log "Done. Environments:" 
conda env list
