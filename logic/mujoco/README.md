# THUAI10 MuJoCo 具身智能原型

本目录提供可选的 MuJoCo / Unitree G1 机器人竞赛后端：固定步长物理、双 RGB-D、29 关节位置控制、检索与对抗裁判、隔离策略执行、练习、循环赛、总榜和轨迹记录。

这是可独立验证的原型，与现有 .NET 10 工程并存。当前仓库的正式 Protobuf / gRPC、Unity 客户端协议尚未实现，本模块不会把自己的 JSON 策略协议冒充为正式通信组接口。后续接入点见 [集成说明](../../docs/mujoco/INTEGRATION.md)。

## 目录分工

| 目录 | 内容 |
| --- | --- |
| `logic/mujoco/` | Python 后端、物理、裁判、配置、世界资源和测试 |
| `interface/mujoco/` | 网页、样式、脚本与界面格式检查 |
| `CAPI/python/mujoco/` | 公开观测 / 动作类型和行走策略示例 |
| `dependency/python/mujoco/` | 固定 Python 依赖和开发工具版本 |
| `dependency/docker/mujoco/` | 统一策略镜像配方 |
| `dependency/shell/mujoco/` | 部署、资源校验、验收和选手包生成工具 |
| `playback/mujoco/` | 轨迹回放入口 |
| `installer/mujoco/` | 现有下载器 / 启动器的实际配置 |
| `docs/mujoco/` | 随原型提交的临时开发文档 |

## Windows 快速启动

需要 Python 3.13、图形驱动和已安装的 Docker Desktop Linux 引擎。在仓库根目录执行：

```powershell
.\dependency\shell\mujoco\deploy.cmd
```

它会在本目录创建 `.venv`、安装固定依赖、下载并校验固定版本资源、构建隔离策略环境，再启动 <http://127.0.0.1:8767>。首次在本机设置管理员，没有默认密码。日常启动使用 `dependency/shell/mujoco/start.cmd`。

管理员生成邀请码，选手从网页下载入门行走包，编写策略后上传 ZIP。检查通过可自动开始城市练习，成绩与回放返回网页。示例提供基本行走和简单深度转向，完整搜索、瞄准、自主起身与避车需要选手实现。练习只评测策略，不更新模型参数。

运行数据、提交、日志和备份在 `logic/mujoco/var/`，下载资源在 `logic/mujoco/third_party/`，测试输出在 `logic/mujoco/artifacts/`，均不进入 Git。服务名称、会话 Cookie、任务名称与容器标签使用独立的 THUAI10 标识。

## 下载器与启动器

生成兼容现有 `installer/catalog-tool` 数据结构的源码选手包：

```powershell
python dependency/shell/mujoco/build_package.py logic/mujoco/artifacts/package-v0.4.0
```

输出包含 `catalog.json`、`payload/` 和源码 ZIP。清单的 `path`、`url`、`size`、`sha256` 与现有下载器对应。源文件使用白名单，原包不会混入账号库、选手代码、虚拟环境或安装记录。可加 `--include-assets` 包含通过锁文件 SHA-256 校验的第三方资源；不要把生成包或模型提交到 Git。

该包不是免安装二进制。使用 .NET 启动器前，先执行 `setup.cmd` 和 `configure-runtime.cmd`，为包创建本机 Python 环境及容器镜像，再由启动器启动 `thuai10-launch.json` 指向的真实程序。完整步骤见 [启动器接入](../../installer/mujoco/README.md)。

## 开发检查

```powershell
python -m pip install -r dependency/python/mujoco/requirements-lock.txt
python -m pip install -r dependency/python/mujoco/requirements-dev.txt
python dependency/shell/mujoco/fetch_assets.py
python -m pytest -c logic/mujoco/pyproject.toml logic/mujoco/tests
python -m ruff check --config logic/mujoco/pyproject.toml logic/mujoco CAPI/python/mujoco dependency/shell/mujoco playback/mujoco
python -m ruff format --check --config logic/mujoco/pyproject.toml logic/mujoco CAPI/python/mujoco dependency/shell/mujoco playback/mujoco
npm ci --ignore-scripts --prefix interface/mujoco
npm run format:check --prefix interface/mujoco
```

Python 使用 UTF-8、4 空格和固定 Ruff 规则，网页使用固定 Prettier 配置。现有 .NET 构建和格式检查继续保留；新增独立的 MuJoCo 检查流程。

真实 Docker / RGB-D 验收工具为 `dependency/shell/mujoco/validate_platform.py`；完整 60 秒城市验收为 `validate_release.py`。这些程序仅创建独立测试目录，不向正式账号库添加测试账号。

## 当前边界

默认单机、单局队列、CPU 推理。PyTorch CPU 环境可由管理员发布；CUDA 环境必须在有可用 NVIDIA 设备的节点通过实际推理检测后才发布。当前开发设备没有完成 GPU 验收。复杂城市在当前设备上慢于实时，完整长局与性能记录保留在原型验收文档。

自己的代码、模型和练习仅本人及管理员可见；正式成绩经管理员发布后在平台内开放。陌生策略只在离线、只读、非 root 的受限容器内执行；本地原生 CLI 只面向受信代码。

本模块自有代码遵循仓库根目录 [MIT 许可](../../LICENSE)。第三方资源的来源、固定版本及许可见 [THIRD_PARTY.md](THIRD_PARTY.md)，下载的资源继续遵循各自许可。
