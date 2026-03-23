#!/usr/bin/env bash
#
# Purpose: Build Docker image for thesis-draft (miniforge-based full env).
# Dependencies: docker (daemon running), git.
# Usage:
#   ./build_docker.sh
#   ./build_docker.sh --no-cache
# Optional docker build-args (prepend to docker build via manual docker build, or extend this script):
#   --build-arg THESIS_PYTHON_VERSION=3.11
#   --build-arg INSTALL_RLDS=0          skip rlds_env
#   --build-arg INSTALL_DEXVLA=0        skip dexvla-robo
#   --build-arg INSTALL_EVAL_ROBOTWIN=0 skip RoboTwin (TinyVLA eval lockfile; largest)
# Expected: image named below; log under logs/ with timestamp.
#
# Compatible with Ubuntu 20.04 LTS+ (bash 4+, date, docker).

set -e

# --- Configurable parameters (edit here) ---
IMAGE_NAME="thesis-draft:miniforge"
DOCKERFILE_PATH="Dockerfile"
BUILD_CONTEXT="."
LOG_DIR="logs"
# Script args are passed to docker build (e.g. ./build_docker.sh --no-cache)
# --- End of configurable parameters ---

# Timestamp UTC+8 for log file name (YYYYMMDDHHMMSS)
log_ts() { TZ=Asia/Shanghai date +%Y%m%d%H%M%S; }
SCRIPT_NAME="build_docker"
LOG_FILE="${LOG_DIR}/${SCRIPT_NAME}_$(log_ts).log"

# ANSI colors for stderr/console (not written to log file)
red='\033[0;31m'
green='\033[0;32m'
blue='\033[0;34m'
yellow='\033[1;33m'
nc='\033[0m'

# Abort if not run from thesis-draft root (no Dockerfile in current dir)
if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
  echo -e "${red}[ERR] Dockerfile not found: ${DOCKERFILE_PATH}. Run from thesis-draft root.${nc}" >&2
  exit 1
fi

mkdir -p "${LOG_DIR}"

log_msg() {
  local level="$1"
  shift
  local msg="[${level}] $*"
  case "${level}" in
    ERR|WARNING) echo -e "${red}${msg}${nc}" ;;
    SUCCESS)     echo -e "${green}${msg}${nc}" ;;
    ARG|URL)     echo -e "${blue}${msg}${nc}" ;;
    *)           echo -e "${yellow}${msg}${nc}" ;;
  esac
  echo "${msg}" >> "${LOG_FILE}"
}

log_success() { log_msg SUCCESS "$@"; }
log_warn()    { log_msg WARNING "$@"; }
log_err()     { log_msg ERR "$@"; }
log_info()    { log_msg INFO "$@"; }
log_arg()     { log_msg ARG "$@"; }

run_build() {
  log_info "Build stage: starting docker build."
  log_arg "IMAGE_NAME=${IMAGE_NAME}"
  log_arg "DOCKERFILE_PATH=${DOCKERFILE_PATH}"
  log_arg "BUILD_CONTEXT=${BUILD_CONTEXT}"
  log_arg "BUILD_EXTRA_ARGS=$*"

  if ! command -v docker &>/dev/null; then
    log_err "docker not found in PATH."
    return 1
  fi

  if ! docker info &>/dev/null; then
    log_err "Docker daemon not running or not permitted."
    return 1
  fi

  if [[ ! -f "${DOCKERFILE_PATH}" ]]; then
    log_err "Dockerfile not found: ${DOCKERFILE_PATH}"
    return 1
  fi

  if [[ ! -d "${BUILD_CONTEXT}" ]]; then
    log_err "Build context dir not found: ${BUILD_CONTEXT}"
    return 1
  fi

  log_info "Build stage: invoking docker build (streaming to terminal and log via tee -a)."
  # tee -a: same output in real time on terminal and appended to LOG_FILE.
  # PIPESTATUS[0] is docker build exit code (tee alone would mask failure under set -e).
  docker build \
    -f "${DOCKERFILE_PATH}" \
    -t "${IMAGE_NAME}" \
    "$@" \
    "${BUILD_CONTEXT}" 2>&1 | tee -a "${LOG_FILE}"
  local build_rc="${PIPESTATUS[0]}"
  if [[ "${build_rc}" -eq 0 ]]; then
    log_success "Build stage: image built successfully."
    return 0
  fi
  log_err "Build stage: docker build failed (exit ${build_rc})."
  return 1
}

# Pass through extra args correctly (e.g. --no-cache)
main() {
  printf 'Log file: %s\n' "${LOG_FILE}" | tee -a "${LOG_FILE}"
  log_info "Script started."

  if run_build "$@"; then
    log_success "Done. Image: ${IMAGE_NAME}"
    exit 0
  else
    log_err "Build failed. See log: ${LOG_FILE}"
    exit 1
  fi
}

main "$@"
