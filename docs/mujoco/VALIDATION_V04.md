# v0.4 验收与边界

历史验收日期：2026-11-20，Windows、Docker Linux 策略容器、MuJoCo 3.3.7。这些记录来自迁入前的独立原型，原始运行数据未随源码迁入。使用独立测试目录和测试账号，未修改正式管理员账号。本次仓库接入的复验另见 [UPSTREAM_VALIDATION.md](UPSTREAM_VALIDATION.md)。

| 检查 | 结果 |
| --- | --- |
| 自动检查 | 72 项全量通过，补充镜像复用回归后相关 11 项通过，共 73 项独立检查 |
| 既有网页与仿真闭环 | 21 项真实集成检查通过，含隔离、自动练习、正式发布、权限与隐藏种子 |
| 新版完整对局与赛制 | 15 项通过，含完整 60 秒城市对局、四场镜像循环赛、总榜发布和备份 |
| PyTorch 上传运行 | 3 项通过，实际使用 PyTorch 2.7.0 完成上传检查和房间仿真 |
| GPU | 当前 Docker 节点无可用 NVIDIA 设备，未发布 CUDA 环境，不声称硬件验收通过 |

## 完整城市对局

先后两次 60 仿真秒城市对局均完成，分别保存 3001 帧有限状态轨迹。新版任务集包含五类物品和干扰物，使用真实双 RGB-D、隔离策略与网页回放。最终配置这一轮耗时 326.33 实际秒；期间同机运行其他测试，不能将其作为独立性能对比。

每名策略完成 3000 次有效响应；平均响应耗时约 21.30 / 25.67 ms，95 分位约 97.42 / 98.54 ms，最大约 220.78 / 249.24 ms。耗时包含通信和等待。每名策略复用约 2400 次未变化图像及 2999 次任务参考图，图像与关节控制频率不变。

入门策略完成实际移动，双方最终生命均为 100，但整局仍记录倒地与一次超时复位。它用于提供可运行起点，不是完整搜索、交通避让或自主起身能力的证明。城市仍慢于实时。

## 公平赛与恢复

两名选手、两组布局，各布局互换出生位置与私人任务组，共四场真实房间比赛完成，并发布积分总榜。单元检查另外覆盖排名、并列、未完成赛事禁止发布、权限、环境一致性与固定版本。

备份检查验证数据库和提交原包快照、SHA-256 校验、安全重新解压及旧会话撤销；恢复只写入全新目录。保留策略验证到期练习文件清理，近期练习和正式比赛保留。自动恢复使用原种子与版本重新运行，不能恢复已经丢失的中间物理进度。

## 网页验收

通过真实网页完成选手登录、发起一局 60 秒房间练习、查看完成结果，并与已有 60 秒城市结果做对比；诊断页显示 3000 次响应统计及生命、耗时曲线。测试账号总榜仅显示已发布赛事，管理员备份按钮实际产生完整快照。最终页面无浏览器 JavaScript 错误，截图留在本地忽略目录。

## 复验

```powershell
.\logic\mujoco\.venv\Scripts\python.exe -m pytest -c logic/mujoco/pyproject.toml logic/mujoco/tests -q
.\logic\mujoco\.venv\Scripts\python.exe dependency/shell/mujoco/validate_platform.py
.\logic\mujoco\.venv\Scripts\python.exe dependency/shell/mujoco/validate_release.py
.\logic\mujoco\.venv\Scripts\python.exe dependency/shell/mujoco/validate_torch_runtime.py
```

以上命令从当前仓库根目录运行，先执行 `dependency/shell/mujoco/setup.cmd`。三项实际集成验收需要可用 Docker 引擎与已下载资源；PyTorch 环境首次构建需要联网。新生成的原始报告保存在忽略的 `logic/mujoco/artifacts/` 目录。不同设备上的速度与数值一致性需要重新验证。
