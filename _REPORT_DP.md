# DP Wrapper + Early Stop 改造报告（中文）

## 1. 目标与约束

本次改造严格围绕你的两项要求：

- 多任务拼接训练，以及对该多任务 ckpt 的单任务评估。
- 早停机制（基于 k 步评估、连续若干次相对提升不足则停训）。

并遵循以下原则：

- 尽可能对齐 `ACT` / `TinyVLA` 的命名、wrapper 思路、配置格式、CLI 入口。
- 对 DP 源码最小改动，不绕路。
- 训练数据保持随机 shuffle。
- 不修改原始数据，只新增衍生数据与中间产物。
- Eval 严格使用 Val 集评估损失，训练与验证集划分沿用 DP 原设定。


## 2. 新增与修改文件清单

### 2.1 新增入口与 Wrapper

- `third_party/RoboTwin/policy/DP/_train.sh`
- `third_party/RoboTwin/policy/DP/_eval.sh`
- `third_party/RoboTwin/policy/DP/_tr_wrapper.py`
- `third_party/RoboTwin/policy/DP/_ev_wrapper.py`

### 2.2 新增配置目录与示例配置

- `third_party/RoboTwin/policy/DP/_tr_cfg/hanging_mug_pair_dryrun.yaml`
- `third_party/RoboTwin/policy/DP/_ev_cfg/hanging_mug_pair_dryrun.yaml`

### 2.3 对 DP 原有代码的最小改动

- `third_party/RoboTwin/policy/DP/diffusion_policy/workspace/robotworkspace.py`
  - 增加早停逻辑（基于 Val loss）。
- `third_party/RoboTwin/policy/DP/diffusion_policy/config/robot_dp_14.yaml`
  - 增加早停参数默认字段。
- `third_party/RoboTwin/policy/DP/diffusion_policy/config/robot_dp_16.yaml`
  - 增加早停参数默认字段。
- `third_party/RoboTwin/policy/DP/deploy_policy.py`
  - 增加可选 `train_task_name` 支持，用于“单任务环境评估 + 联合任务权重加载”。
- `third_party/RoboTwin/policy/DP/deploy_policy.yml`
  - 增加 `train_task_name: null`。


## 3. 与 ACT/TinyVLA 的对齐策略与决策理由

### 3.1 文件命名与入口形态

对齐点：

- `ACT/TinyVLA` 使用 `_train.sh`、`_eval.sh` + `_tr_wrapper.py`、`_ev_wrapper.py`。
- DP 同步采用同一命名体系。

理由：

- 统一跨 policy 的使用心智模型，减少切换成本。
- 满足你要求的 CLI 形式：`_train.sh <config-name>` 与 `_eval.sh <config-name>`。


### 3.2 Wrapper 构建思路

对齐点：

- `ACT/TinyVLA`：wrapper 负责解析 YAML、拼接多任务语义、构造底层命令、落地运行元信息。
- DP 也采用 wrapper 统筹，不把多任务拼接硬塞进底层训练主干。

理由：

- 对 DP 原有训练代码侵入最小。
- 逻辑可追踪，且兼容原 `train.sh/eval.sh` 老入口。


### 3.3 配置格式和变量命名

对齐点（核心字段）：

- `TRAIN_TASKS` / `EVAL_TASKS`（每行 `[task_name, task_config, expert_num]`）
- `TRAIN_SEED` / `TRAIN_GPU_ID`
- `EVAL_SEED` / `EVAL_GPU_ID`
- `EARLY_STOP_PATIENCE_EVALS`
- `EARLY_STOP_REL_TOL`
- `EVAL_STEPS_FOR_EARLY_STOP`

DP 额外保留字段（因框架差异必须）：

- `TRAIN_ACTION_DIM`（DP 需选择 `robot_dp_14.yaml` / `robot_dp_16.yaml`）。
- 其他训练超参（batch size、epoch、lr 等）以 `TRAIN_*` 命名传递。

理由：

- 最大化和 ACT/TinyVLA 的语义一致性。
- 兼顾 DP 的原生配置依赖（action dim）。


### 3.4 训练数据拼接实现方式

实际实现：

- 对每个 `TRAIN_TASKS` 子任务，先保证单任务 zarr 存在（不存在就调用 `process_data.py` 生成）。
- wrapper 读取多个源 zarr，拼接 `head_camera/state/action/episode_ends`，生成新的联合 zarr。
- 源 zarr 与原始 hdf5 均不改写。

为何不直接改原始流程：

- DP 现有 `process_data.py` 是“单任务 -> 单 zarr”模式，直接强改会扩大入侵面。
- 采用“新增联合 zarr”是最短路径，且保留原数据严格对应关系。


### 3.5 随机 shuffle 与数据不改动

随机性：

- DP 原配置 `dataloader.shuffle: True` 继续保留。
- dataloader 的 batch sampler 仍使用随机置换逻辑。

数据不改动：

- 不修改任何已有单任务 zarr/hdf5。
- 仅新增联合 zarr（衍生产物）。


### 3.6 多任务 ckpt 的单任务评估

问题本质：

- DP 原 `deploy_policy.py` 使用 `task_name` 拼接 ckpt 路径。
- 联合训练时 ckpt 目录名是联合 task slug，若直接单任务 eval 会找不到权重。

改法（最小）：

- 给 `deploy_policy.py` 增加可选 `train_task_name`。
- 评估时：
  - `task_name` 仍是单任务（决定环境/指令/评估目录）。
  - `train_task_name` 指向联合 task slug（决定加载哪个 ckpt）。

理由：

- 不破坏单任务评估原行为（默认回退为 `task_name`）。
- 精准满足“联合 ckpt -> 单任务 eval”要求。


## 4. 早停机制实现细节（对齐 ACT/TinyVLA）

### 4.1 触发条件与参数

新增训练参数（位于 `training.*`）：

- `early_stop_patience_evals`
- `early_stop_rel_tol`
- `eval_steps_for_early_stop`

启用条件：

- `early_stop_patience_evals > 0` 且 `early_stop_rel_tol > 0.0`

提升判定：

- `rel_improve = (best_val_loss - curr_val_loss) / max(abs(best_val_loss), 1e-12)`
- 当 `rel_improve > early_stop_rel_tol` 视为有效提升，否则累计“无提升次数”。

停止条件：

- 连续无提升次数 `>= early_stop_patience_evals` 立即早停。


### 4.2 先训练后评估时序

实现位置：

- `robotworkspace.py` 的 epoch 主循环中，顺序仍为：
  - 先 train
  - 后 validation
  - 再基于 val_loss 决策是否 early stop

这与 `ACT/TinyVLA` 的“训练推进后再看评估结果”的时序一致。


### 4.3 Eval 使用 Val 集而非 Train 集

当前 DP 本就有：

- `dataset.get_validation_dataset()`
- `val_dataloader` 独立于 train_dataloader

本次早停直接基于 `val_dataloader` 的 `val_loss`，未引入 train 集替代评估。


### 4.4 Train/Val 划分比例

沿用 DP 原有默认：

- `task.dataset.val_ratio: 0.02`

并允许在 wrapper 中通过 `TRAIN_VAL_RATIO` 显式覆盖，默认仍对齐原实现（简单且不绕路）。


## 5. 关键运行路径（使用方式）

### 5.1 多任务训练

- 配置：`policy/DP/_tr_cfg/<name>.yaml`
- 运行：`bash policy/DP/_train.sh <name>`

### 5.2 多任务 ckpt 的单任务/多任务评估

- 配置：`policy/DP/_ev_cfg/<name>.yaml`
- 运行：`bash policy/DP/_eval.sh <name>`
- `EVAL_TASKS` 可写一个任务（单任务评估）或多个任务（批量评估）。


## 6. 为什么这是“针对于 DP 原始代码的简单方法”

- 没有重构 DP 主训练入口 `train.py`。
- 没有重写 DP 数据结构与采样器。
- 仅在 wrapper 层完成多任务拼接和命令编排。
- 仅在 `robotworkspace.py` 增加必要早停判断，不改变训练主流程骨架。
- 对部署评估仅加 1 个可选字段（`train_task_name`）实现联合 ckpt 兼容。


## 7. 已验证项

- 新增/修改文件已完成静态检查（无 linter 报错）。
- wrapper、配置、早停参数链路在代码层已贯通。


## 8. 后续建议（可选）

- 用一个小规模 dry-run 配置跑通端到端：
  - 训练 1~2 epoch；
  - 在 `EVAL_TASKS` 放 1~2 个任务验证联合 ckpt 加载路径；
  - 再调大训练规模。

- 若后续希望进一步与 ACT/TinyVLA 完全同构，可再增加：
  - 更细粒度 run manifest 字段；
  - 统一更多 `TRAIN_*` 参数命名到相同集合。
