#!/usr/bin/env bash
set -euo pipefail

# Sync current repository to remote host BAAI-emllm using rclone.
# Usage:
#   scripts/push.sh
#   scripts/push.sh --dry-run
#   scripts/push.sh --remote-dir thesis-draft-dev-backup
#   scripts/push.sh --project-root /path/to/repo --remote-dir my-project
#
# @input:
#   - CLI args:
#       --project-root [string, absolute/relative path, existing directory]
#       --remote [string, rclone remote name, default: BAAI-emllm]
#       --remote-dir [string, path under remote root, default: current directory name]
#       --ignore-file [string, path to ignore file, default: .rcloneignore; gitignore-like, "!" negates]
#       --dry-run [flag, no data changes]
# @output:
#   - Exit 0 on success, non-zero on failure.
#   - Prints sync summary and destination.
#   - Writes detailed logs in real time to <project-root>/rclone.log (--log-file).
# @scenario:
#   - Keep this project synchronized to a remote storage/server via rclone.
#
# Sync policy (see .rcloneignore, gitignore-like):
#   - Paths matched by exclude rules (lines without leading "!") are out of scope:
#     not uploaded from local, not compared, and not deleted on remote unless
#     you pass rclone's --delete-excluded (this script never adds it).
#   - Lines starting with "!" are include/negation rules: those paths stay in the
#     synced set even when a broader exclude would hide them (first matching
#     filter rule wins; include rules are written before excludes).
#   - Everything else is mirrored strictly: rclone sync adds missing files,
#     updates changed files, and deletes extra files on the remote so the
#     destination matches local for in-scope paths only. No --update: local is
#     the source of truth when size/modtime differ.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DEFAULT_PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

PROJECT_ROOT="${DEFAULT_PROJECT_ROOT}"
REMOTE_NAME="BAAI-emllm"
REMOTE_BASE_DIR="/home/shwu/zylong/mnt/BAAI-emllm"
REMOTE_DIR=""
IGNORE_FILE=""
DRY_RUN="false"

print_usage() {
  cat <<'EOF'
Usage:
  scripts/push.sh [options]

Options:
  --project-root <path>  Project root to sync. Default: repo root of this script.
  --remote <name>        Rclone remote name. Default: BAAI-emllm.
  --remote-dir <path>    Full destination path under remote.
                         Default: /home/shwu/zylong/mnt/BAAI-emllm/<project-dir-name>.
  --ignore-file <path>   Rclone ignore file. Default: <project-root>/.rcloneignore.
  --dry-run              Show planned changes without modifying remote.
  -h, --help             Show this help and exit.
EOF
}

ensure_command() {
  local cmd="$1"
  if ! command -v "${cmd}" >/dev/null 2>&1; then
    echo "[ERROR] Required command not found: ${cmd}" >&2
    exit 1
  fi
}

build_rclone_filter_file() {
  local ignore_file="$1"
  local filter_file="$2"
  local line=""
  local rule=""
  local -a include_rules=()
  local -a exclude_rules=()

  : >"${filter_file}"
  while IFS= read -r line || [[ -n "${line}" ]]; do
    # Skip comments and blank lines.
    if [[ -z "${line}" || "${line}" == \#* ]]; then
      continue
    fi

    # Gitignore-style negation: "!" forces path back into the synced set.
    if [[ "${line}" == !* ]]; then
      rule="${line#!}"
      include_rules+=("${rule}")
      continue
    fi

    exclude_rules+=("${line}")
    # Plain path (no glob chars): also exclude descendants.
    if [[ "${line}" != *"*"* && "${line}" != *"?"* && "${line}" != *"["* ]]; then
      if [[ "${line}" == */ ]]; then
        exclude_rules+=("${line}**")
      else
        exclude_rules+=("${line}/**")
      fi
    fi
  done <"${ignore_file}"

  for rule in "${include_rules[@]}"; do
    printf '+ %s\n' "${rule}" >>"${filter_file}"
  done
  for rule in "${exclude_rules[@]}"; do
    printf -- '- %s\n' "${rule}" >>"${filter_file}"
  done
}

parse_args() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --project-root)
        [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for --project-root" >&2; exit 1; }
        PROJECT_ROOT="$2"
        shift 2
        ;;
      --remote)
        [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for --remote" >&2; exit 1; }
        REMOTE_NAME="$2"
        shift 2
        ;;
      --remote-dir)
        [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for --remote-dir" >&2; exit 1; }
        REMOTE_DIR="$2"
        shift 2
        ;;
      --ignore-file)
        [[ $# -ge 2 ]] || { echo "[ERROR] Missing value for --ignore-file" >&2; exit 1; }
        IGNORE_FILE="$2"
        shift 2
        ;;
      --dry-run)
        DRY_RUN="true"
        shift
        ;;
      -h|--help)
        print_usage
        exit 0
        ;;
      *)
        echo "[ERROR] Unknown argument: $1" >&2
        print_usage >&2
        exit 1
        ;;
    esac
  done
}

main() {
  parse_args "$@"
  ensure_command "rclone"

  PROJECT_ROOT="$(cd "${PROJECT_ROOT}" && pwd)"
  if [[ ! -d "${PROJECT_ROOT}" ]]; then
    echo "[ERROR] Project root does not exist: ${PROJECT_ROOT}" >&2
    exit 1
  fi
  if [[ -z "${REMOTE_DIR}" ]]; then
    REMOTE_DIR="${REMOTE_BASE_DIR%/}/$(basename "${PROJECT_ROOT}")"
  fi

  if [[ -z "${IGNORE_FILE}" ]]; then
    IGNORE_FILE="${PROJECT_ROOT}/.rcloneignore"
  fi
  if [[ -f "${IGNORE_FILE}" ]]; then
    IGNORE_FILE="$(cd "$(dirname "${IGNORE_FILE}")" && pwd)/$(basename "${IGNORE_FILE}")"
  else
    echo "[WARN] Ignore file not found, continue without it: ${IGNORE_FILE}"
    IGNORE_FILE=""
  fi

  local dst="${REMOTE_NAME}:${REMOTE_DIR}"
  local filter_file=""
  local -a cmd=(
    rclone sync
    "${PROJECT_ROOT}/"
    "${dst}"
    --progress
    --fast-list
    --transfers 8
    --checkers 16
    --links
  )

  if [[ -n "${IGNORE_FILE}" ]]; then
    filter_file="$(mktemp)"
    trap '[[ -n "${filter_file:-}" && -f "${filter_file:-}" ]] && rm -f "${filter_file:-}"' EXIT
    build_rclone_filter_file "${IGNORE_FILE}" "${filter_file}"
    cmd+=(--filter-from "${filter_file}")
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    cmd+=(--dry-run)
  fi

  echo "[INFO] Source: ${PROJECT_ROOT}/"
  echo "[INFO] Destination: ${dst}"
  if [[ -n "${IGNORE_FILE}" ]]; then
    echo "[INFO] Ignore file: ${IGNORE_FILE}"
  fi
  if [[ "${DRY_RUN}" == "true" ]]; then
    echo "[INFO] Running in dry-run mode"
  fi

  # Detailed, line-buffered-style log file (rclone flushes continuously). DEBUG is max practical level but too much, use info now.
  local log_file="${PROJECT_ROOT}/logs/rclone.log"
  mkdir -p "${PROJECT_ROOT}/logs"
  {
    printf '%s\n' "===== push.sh run start $(date -u +"%Y-%m-%dT%H:%M:%SZ") UTC ====="
    printf '%s\n' "source=${PROJECT_ROOT}/ destination=${dst} dry_run=${DRY_RUN}"
  } >>"${log_file}"

  cmd+=(
    --log-file "${log_file}"
    --log-level INFO
    --stats-log-level INFO
  )

  echo "[INFO] Verbose log (append): ${log_file}"

  "${cmd[@]}"
  echo "[INFO] Sync completed successfully."
}

main "$@"
