# MuJoCo Python 依赖

- `requirements-lock.txt`：Python 3.13 后端、ONNX 推理与自动检查的固定依赖。
- `requirements-dev.txt`：固定 Ruff 0.17.6，用于 Python 格式和静态检查。

从仓库根目录运行 `dependency/shell/mujoco/setup.cmd` 安装。依赖只进入 `logic/mujoco/.venv/`；不要提交该目录。选手容器内的依赖另由 `dependency/docker/mujoco/` 固定，不执行选手安装脚本。
