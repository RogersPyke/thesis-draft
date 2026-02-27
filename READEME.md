在 RoboTwin 框架中自定义一个环境和任务，主要涉及资产准备、环境逻辑实现、任务配置以及数据生成四个核心步骤。以下是详细的操作指南：

### 1. 准备模型资产 (Assets)
所有的物体模型都需要放置在 `third_party/RoboTwin/assets/objects/` 目录下。
- **目录结构**：为你的物体创建一个文件夹，例如 `my_object/`。
- **模型文件**：放入 `.obj` 或 `.glb` 格式的模型文件。
- **元数据配置**：在该目录下创建 `model_data.json`（或针对不同编号的 `model_data0.json`），定义以下关键信息：
  - `scale`: 物体的缩放比例。
  - `contact_points_pose`: 定义抓取点（4x4 矩阵列表）。机器人抓取时会参考这些点。
  - `functional_matrix`: 定义物体的功能点（例如瓶口、工具尖端）。
  - `extents`: 物体的包围盒尺寸。

### 2. 创建环境逻辑类 (Environment Implementation)
在 `third_party/RoboTwin/envs/` 目录下创建一个新的 Python 文件（例如 `my_task.py`）。

你需要继承 `Base_Task` 类，并实现以下核心方法：
- **类名与文件名一致**：类名必须与文件名相同，以便 `collect_data.py` 动态加载。
- **`setup_demo(self, **kwargs)`**：
  调用 `super()._init_task_env_(**kwargs)` 初始化基础环境。
- **`load_actors(self)`**：
  使用 `rand_create_actor` 或 `create_actor` 加载你准备好的物体到场景中。
  ```python
  self.obj = rand_create_actor(self, modelname="my_object", xlim=[...], ylim=[...], ...)
  ```
- **`play_once(self)`**：
  编写“专家策略”脚本。使用框架提供的 API 描述机器人完成任务的过程：
  - `self.grasp_actor(actor, arm_tag)`：生成抓取动作。
  - `self.move(actions)`：执行动作序列。
  - `self.place_actor(...)`：生成放置动作。
  - `self.move_by_displacement(x, y, z)`：相对位移。
- **`check_success(self)`**：
  定义任务成功的判定逻辑（例如物体的坐标或姿态是否达到目标范围）。

参考示例：`third_party/RoboTwin/envs/adjust_bottle.py`。

### 3. 创建任务配置文件 (Task Configuration)
在 `third_party/RoboTwin/task_config/` 目录下创建一个 YAML 文件（例如 `my_config.yml`）。

你可以参考 `demo_clean.yml`，设置以下参数：
- `episode_num`: 想要生成的轨迹数量。
- `embodiment`: 选用的机器人型号（如 `[aloha-agilex]`）。
- `domain_randomization`: 是否开启背景、灯光、杂物等的随机化。
- `camera`: 开启哪些摄像头（head_camera, wrist_camera）。
- `data_type`: 保存的数据种类（rgb, qpos, endpose 等）。

### 4. 运行与数据采集
使用项目根目录下的脚本启动采集过程：

```bash
# 格式：bash collect_data.sh <任务名称> <配置文件名> <GPU_ID>
bash collect_data.sh my_task my_config 0
```

### 5. (可选) 自定义任务描述
如果你需要为任务生成自然语言指令：
- 在 `third_party/RoboTwin/description/task_instruction/` 下添加对应的指令模板。
- 采集完成后，系统会自动运行 `gen_episode_instructions.sh` 来关联动作轨迹与文字描述。

### 总结清单
| 步骤 | 对应路径 |
| :--- | :--- |
| **资产** | `assets/objects/<object_name>/` (包含模型和 `.json`) |
| **环境** | `envs/<task_name>.py` (继承 `Base_Task`) |
| **配置** | `task_config/<config_name>.yml` |
| **执行** | 运行 `collect_data.sh` |