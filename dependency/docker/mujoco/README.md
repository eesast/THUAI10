# MuJoCo 策略镜像

- `Dockerfile`：统一 Python 3.13 / NumPy / Pillow / ONNX Runtime CPU 环境。
- `Dockerfile.torch`：在基础镜像上增加固定 PyTorch CPU 环境。
- `Dockerfile.cuda`：可选 PyTorch CUDA / ONNX Runtime GPU 环境，需要可用 NVIDIA 设备。

基础镜像的构建上下文是 `logic/mujoco/`，由部署程序传入本目录的 Dockerfile 路径。容器只获得选手自身提交，使用独立 THUAI10 标签，不与其他平台共用清理标签。镜像使用后固定摘要，不覆盖历史环境。

部署入口为 `dependency/shell/mujoco/configure-runtime.cmd` 或网页管理员的运行环境页面。

- `Dockerfile.test`：CI 的 Linux 无界面测试环境，用 Xvfb / Mesa 运行真实渲染检查；构建上下文是仓库根目录，对应的 `.dockerignore` 仅允许模块源码及公开资源。

从仓库根目录复验 Linux 环境：

```powershell
docker build -f dependency/docker/mujoco/Dockerfile.test -t thuai10-mujoco-tests .
docker run --init --rm --network none --shm-size=512m thuai10-mujoco-tests
```

`--init` 让 Xvfb 的启动通知和子进程回收正常工作；测试阶段关闭网络，构建阶段下载固定依赖和经校验的公开资源。
