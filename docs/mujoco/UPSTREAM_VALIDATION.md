# THUAI10 接入验收（临时开发文档）

日期：2026-11-20。基于组织 `dev` 的 `0f89c629e8b98152459fa842ff2684f6bee6262a`，功能分支为 `codex/mujoco-arena-integration`。本记录只列本次迁入后的实际复验，迁入前的长局与界面历史记录另见 [VALIDATION_V04.md](VALIDATION_V04.md)。

## 仓库规范与分工

- 后端、网页、选手接口、依赖、回放和启动配置分别进入 `logic`、`interface`、`CAPI/python`、`dependency`、`playback` 和 `installer` 对应子目录。
- Python 使用 UTF-8、4 空格和固定 Ruff 规则；网页使用固定版本的 Prettier。原有根目录策略、许可、C# 工程和 .NET 工作流保留。
- 运行数据、账号库、提交包、虚拟环境、第三方下载、生成包与测试输出不进入 Git。
- 本目录是随代码提供的临时开发文档，正式文档仍按 `docs/README.md` 的流程维护。

## 已完成的本机复验

| 检查 | 结果 |
| --- | --- |
| Windows Python 自动检查 | 全部 76 项通过，涵盖物理、赛制、权限、环境、恢复、提交与分发包 |
| Linux 无界面自动检查 | 全部 76 项通过，离线容器中使用 Xvfb / Mesa，实际运行 75.03 秒 |
| Python / 网页格式 | Ruff 检查与格式检查、Prettier 检查通过 |
| PowerShell 入口 | 所有入口解析通过，实际运行 `setup.ps1` 创建独立环境并安装固定依赖 |
| 既有 .NET 工程 | `logic`、`playback`、`installer` 的 .NET 10 Release 构建与格式检查通过 |
| 既有启动器测试 | 续传、暂停、哈希、更新检查、本地修改保护、安全路径及启动 / 停止通过 |
| 分发清单兼容性 | Python 打包清单与原生 `installer/catalog-tool` 的路径、大小、SHA-256 逐项匹配 |
| 真实 Docker + MuJoCo 闭环 | 全部 21 项通过，独立测试目录，不创建正式账号 |
| 真实网页操作 | 测试账号登录、选择 ZIP、上传、自动练习、成绩与真实回放播放通过，未记录浏览器脚本错误 |

21 项真实闭环包含：管理员部署和真实 RGB-D / 关节通信自检、全包编译错误定位、错误关节数拒绝、两份策略初始化及三次动作检查、宿主提交目录只读、上传后自动城市练习、真实回放保存与读取、显式关节重排适配、正式比赛结算与发布、跨选手权限和隐藏种子过滤。城市练习为 2 仿真秒，用于验证链路，不代表完成长局或完整自主搜索。

网页操作使用独立的临时服务、账号库和 Cookie。浏览器练习为 1 仿真秒，页面显示已完成并可播放真实城市画面；默认正式练习仍为 60 仿真秒。截图保存在忽略目录 `logic/mujoco/artifacts/platform_validation/ui-upstream/`。自动检查保留一条依赖提供的 Starlette / httpx 弃用提示，不影响测试通过。

复验入口：

```powershell
.\dependency\shell\mujoco\setup.cmd
.\logic\mujoco\.venv\Scripts\python.exe -m pytest -c logic/mujoco/pyproject.toml logic/mujoco/tests -q
.\logic\mujoco\.venv\Scripts\python.exe dependency/shell/mujoco/validate_platform.py
```

Linux 无界面测试使用独立容器及 Xvfb / Mesa，命令见 [镜像说明](../../dependency/docker/mujoco/README.md)。CI 对拉向 `dev` 的 PR 执行 Python、网页与 Linux 检查；手动运行工作流还会生成白名单源码分发包。

## 接入边界

本次提供可选 MuJoCo 原型，不包含尚未定义的正式 Protobuf / gRPC / Unity 对接。分发包是需要 Python 3.13 和 Docker 的源码包，不是免安装二进制；没有发布下载服务器。

本机未完成 NVIDIA GPU 硬件验收。练习用于自测，不优化模型权重。复杂城市没有实时速度保证，入门行走策略仍需选手完善搜索、避车、瞄准与自主起身。跨硬件逐位一致性与公网容量未在本次复验中验证。

按贡献指南，通过个人 Fork 向组织 `dev` 提交 PR，等待至少一名成员审阅后合并。
