# rclone 同步使用说明

本文档说明如何将当前项目同步到远程 `BAAI-emllm`。

## 1. 前置条件

- 已安装 `rclone`
- 已完成远程配置，且可在 `rclone listremotes` 中看到 `BAAI-emllm:`

可先执行：

```bash
rclone listremotes
```

若输出中包含 `BAAI-emllm:`，说明远程配置可用。

## 2. 忽略规则

项目根目录包含 `.rcloneignore`，用于排除以下内容：

- `.git` 元数据
- Python 缓存与虚拟环境目录
- 日志与临时文件
- 常见 IDE 配置目录
- 常见系统垃圾文件

你可以按需编辑该文件。

## 3. 同步脚本

脚本路径：

```bash
scripts/push.sh
```

先给执行权限：

```bash
chmod +x scripts/push.sh
```

### 3.1 默认同步（推荐）

在仓库根目录执行：

```bash
scripts/push.sh
```

默认行为：

- 源目录：当前项目根目录
- 目标目录：`BAAI-emllm:/home/zylong/mnt/BAAI-emllm/<当前项目目录名>`
- 忽略文件：`.rcloneignore`
- 同步策略：严格差量同步（仅更新有变化的文件），并保持目标目录与源目录一致

### 3.2 先预览变更（不真正上传）

```bash
scripts/push.sh --dry-run
```

### 3.3 自定义远程目录

```bash
scripts/push.sh --remote-dir thesis-draft-dev-backup
```

### 3.4 指定其他远程（可选）

```bash
scripts/push.sh --remote some-other-remote
```

## 4. 注意事项

- 脚本使用 `rclone sync`：目标端会与源目录保持一致，多余文件会被删除。
- 默认目标路径最终会落在：`/home/zylong/mnt/BAAI-emllm/thesis-draft-dev`。
- 脚本开启了 `--update`，不会重传未变化或目标端更新的文件。
- 建议首次使用时先执行 `--dry-run` 确认变更。
