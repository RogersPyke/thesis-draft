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

# --- robotwin-act: layered ACT stack (conda explicit @EXPLICIT URLs, then pip lock) ---
# Source: policy/ACT/env_requ/conda_requirements.txt then policy/ACT/env_requ/pip_requirements.txt
ACT_ENV_REQU="${RW}/policy/ACT/env_requ"
if [[ ! -f "${ACT_ENV_REQU}/conda_requirements.txt" ]] || [[ ! -f "${ACT_ENV_REQU}/pip_requirements.txt" ]]; then
  echo "[docker_conda_envs] ERROR: missing ${ACT_ENV_REQU}/conda_requirements.txt or pip_requirements.txt" >&2
  exit 1
fi
log "Creating env: robotwin-act (conda --file env_requ/conda_requirements.txt)"
conda create -n robotwin-act --file "${ACT_ENV_REQU}/conda_requirements.txt" -y
log "Installing env: robotwin-act pip deps (env_requ/pip_requirements.txt)"
conda run -n robotwin-act pip install --no-cache-dir -r "${ACT_ENV_REQU}/pip_requirements.txt"

# nvidia-curobo: PyPI has no real wheels for NVlabs cuRobo; install editable from submodule.
# --no-build-isolation: curobo's build needs the env's torch importable (see NVlabs/curobo docs).
CUROBO_SRC="${RW}/script/curobo"
if [[ ! -f "${CUROBO_SRC}/setup.cfg" ]]; then
  echo "[docker_conda_envs] ERROR: cuRobo missing at ${CUROBO_SRC} (init git submodule script/curobo)" >&2
  exit 1
fi
log "Installing nvidia-curobo (editable) from ${CUROBO_SRC} with pip --no-build-isolation"
conda run -n robotwin-act pip install --no-cache-dir --no-build-isolation -e "${CUROBO_SRC}"

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
