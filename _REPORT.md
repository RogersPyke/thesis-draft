# TinyVLA/ACT Dry-run Work Report

## Scope

This report summarizes:

- Code/config changes I made in this round.
- Runtime operations and dry-run test attempts.
- Environment package installation operations.
- Revert action requested by user: disable Python user-site fallback and force env-only dependency resolution.


## Code Changes

### TinyVLA task/config related

1. Updated `third_party/RoboTwin/policy/TinyVLA/aloha_scripts/constants.py`
   - Added `unhanging_mug` into `TASK_CONFIGS`.
   - Dataset path used:
     - `/data/robotiwin/policy/TinyVLA/data/sim-unhanging_mug/demo_clean-100`

2. Added TinyVLA dry-run training configs:
   - `third_party/RoboTwin/policy/TinyVLA/_tr_cfg/hanging_mug_single_dryrun.yaml`
   - `third_party/RoboTwin/policy/TinyVLA/_tr_cfg/hanging_mug_pair_dryrun.yaml`

3. Added TinyVLA dry-run eval configs:
   - `third_party/RoboTwin/policy/TinyVLA/_ev_cfg/hanging_mug_single_dryrun.yaml`
   - `third_party/RoboTwin/policy/TinyVLA/_ev_cfg/hanging_mug_pair_dryrun.yaml`

4. Updated eval wrapper override mapping:
   - `third_party/RoboTwin/policy/TinyVLA/_ev_wrapper.py`
   - Added support for passing `EVAL_TEST_NUM` from yaml to `script/eval_policy.py` as `--test_num`.


### Wrapper/entrypoint behavior adjustments

1. Updated `third_party/RoboTwin/policy/TinyVLA/_tr_wrapper.py`
   - Non-deepspeed path now launches subprocess with `sys.executable` (instead of hardcoded `python3`), to ensure interpreter consistency with current conda env.

2. Updated `third_party/RoboTwin/policy/TinyVLA/_ev_wrapper.py`
   - Added `PYTHONPATH` injection to include TinyVLA root path for `from vla import ...` import resolution when running from repo root.

3. Updated shell entry scripts:
   - `third_party/RoboTwin/policy/TinyVLA/_train.sh`
   - `third_party/RoboTwin/policy/TinyVLA/_eval.sh`


## Revert Requested: PythonUserSite Fallback

User requested:

- Do NOT fallback to user-site packages.
- All deps should be resolved from active conda env only.

I reverted Python user-site fallback behavior and restored strict mode:

1. `third_party/RoboTwin/policy/TinyVLA/_train.sh`
   - Restored:
     - `export PYTHONNOUSERSITE=1`

2. `third_party/RoboTwin/policy/TinyVLA/_eval.sh`
   - Restored:
     - `export PYTHONNOUSERSITE=1`

3. `third_party/RoboTwin/policy/TinyVLA/_tr_wrapper.py`
   - Restored:
     - `env["PYTHONNOUSERSITE"] = "1"`

4. `third_party/RoboTwin/policy/TinyVLA/_ev_wrapper.py`
   - Restored:
     - `env["PYTHONNOUSERSITE"] = "1"`


## Runtime Test Operations Summary

### TinyVLA training dry-run

1. Single-task dry-run (`hanging_mug_single_dryrun`) executed in `dexvla-robo`.
   - Training run reached completion with generated artifacts under:
     - `third_party/RoboTwin/policy/TinyVLA/tinyvla_ckpt/tinyvla-hanging_mug/demo_clean-100`

2. Joint-task dry-run (`hanging_mug_pair_dryrun`) executed in `dexvla-robo`.
   - Joint output generated under:
     - `third_party/RoboTwin/policy/TinyVLA/tinyvla_ckpt/tinyvla-hanging_mug__unhanging_mug/demo_clean__demo_clean-200`

3. Data-only forward smoke tests (non-env rollout):
   - Single-task checkpoint: forward succeeded after device/dtype alignment.
   - Joint checkpoint on both tasks (`hanging_mug`, `unhanging_mug`): forward succeeded.


### TinyVLA env rollout eval attempts

1. `robotwin-tinyvla-eval` and `dexvla-robo` were both tried for env eval.
2. Multiple non-OOM dependency/import blockers appeared during rollout path (e.g. `transformers`, `vla` path, `timm`, `diffusers` compatibility chain, `sapien` in other env).
3. Eval path stabilization was in progress; this report records the operations and revert request implementation.


## Environment Package Installation Operations

All commands were executed via conda env python/pip calls.

### In `dexvla-robo`

1. Attempted/install operations:
   - `PyYAML`
   - `typing_extensions`

2. Notes:
   - Earlier runs observed package resolution from user-site; this is why strict `PYTHONNOUSERSITE=1` has now been restored per user request.
   - With strict mode restored, any missing dep must now be installed directly into the target conda env.


### In `robotwin-tinyvla-eval`

1. Installed:
   - `transformers` (then pinned to `4.45.2`)
   - `timm`
   - `diffusers`

2. Observed pip resolver warnings (not auto-fixed):
   - `robocoin` dependency mismatches, including:
     - missing `opencv-python-headless`
     - torchvision version mismatch relative to robocoin constraints
   - These were warnings during installation and may still impact runtime compatibility.


## Additional Notes

1. Some long-running TinyVLA training subprocesses remained in background during iterative debugging.
   - They were explicitly terminated to free GPU memory before reruns.

2. Lint check performed on edited TinyVLA files:
   - No linter errors were reported for modified files.


## Final State After This Request

- `_REPORT.md` created with full modification/operation summary.
- Python user-site fallback has been reverted.
- TinyVLA wrappers and entry scripts now enforce `PYTHONNOUSERSITE=1` again.
- Environment dependency handling is now strictly env-local as requested.

