# thesis-draft + RoboTwin: multiple conda envs on miniforge.
#
# Environments (default build):
#   thesis         Python 3.11 + third_party/RoboTwin/script/requirements.txt (sim / scripts)
#   robotwin-act   ACT full stack: conda create --file policy/ACT/requirements.txt (+ pytorch/nvidia/conda-forge)
#   rlds_env       openvla-oft RLDS dataset builder (environment_ubuntu.yml)
#   dexvla-robo    TinyVLA / DexVLA training lockfile (Train_Tiny_DexVLA_train.yml; same spec in both dirs)
#   RoboTwin       TinyVLA eval lockfile (Eval_Tiny_DexVLA_environment.yml; Tsinghua mirror lines stripped)
#
# GPU: install PyTorch+CUDA inside envs; run with --gpus all and a matching host driver (NVIDIA Container Toolkit).
# Large paths: see .dockerignore (root .gitignore + aggregated third_party/RoboTwin/** .gitignore rules + Docker-only). Mount data at runtime if needed.
#
# Build options (optional, all default 1):
#   docker build --build-arg INSTALL_RLDS=0 ...
#   docker build --build-arg INSTALL_DEXVLA=0 ...
#   docker build --build-arg INSTALL_EVAL_ROBOTWIN=0 ...

FROM condaforge/miniforge3:latest AS base

ARG THESIS_PYTHON_VERSION=3.11
ARG INSTALL_RLDS=1
ARG INSTALL_DEXVLA=1
ARG INSTALL_EVAL_ROBOTWIN=1

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=UTC
ENV MUJOCO_GL=egl
ENV PYTHONUNBUFFERED=1
ENV CONDA_ALWAYS_YES=true

# OS packages: render/OpenGL, media, and common build tools for pip/conda native extensions
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    cmake \
    ca-certificates \
    curl \
    git \
    git-lfs \
    wget \
    ffmpeg \
    libosmesa6-dev \
    libgl1 \
    libegl1 \
    libglib2.0-0 \
    libsm6 \
    libxext6 \
    libxrender1 \
    libglew-dev \
    libglfw3-dev \
    libgles2-mesa-dev \
    && rm -rf /var/lib/apt/lists/*

# Faster solves; required for some large envs
RUN conda install -n base -y conda-libmamba-solver \
    && conda config --set solver libmamba

WORKDIR /workspace/thesis-draft

# Full tree (keep .git for submodule init when building from a git checkout)
COPY . .

RUN git submodule update --init --recursive \
    && chmod +x scripts/docker_conda_envs.sh

ENV THESIS_ROOT=/workspace/thesis-draft
ENV ROBOTWIN_ROOT=/workspace/thesis-draft/third_party/RoboTwin
ENV PYTHONPATH="${ROBOTWIN_ROOT}:${ROBOTWIN_ROOT}/policy:${PYTHONPATH}"

RUN THESIS_PYTHON_VERSION="${THESIS_PYTHON_VERSION}" \
    INSTALL_RLDS="${INSTALL_RLDS}" \
    INSTALL_DEXVLA="${INSTALL_DEXVLA}" \
    INSTALL_EVAL_ROBOTWIN="${INSTALL_EVAL_ROBOTWIN}" \
    ./scripts/docker_conda_envs.sh

WORKDIR /workspace/thesis-draft/third_party/RoboTwin

ENV PATH="/opt/conda/envs/thesis/bin:$PATH"

CMD ["conda", "run", "-n", "thesis", "/bin/bash"]
