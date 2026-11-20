# MuJoCo 原型接入说明（临时开发文档）

本文随开发代码保存在本仓库，供本次评审与本地验证使用。正式赛事文档仍按 `docs/README.md` 的要求提交到 `eesast/docs`，本次不改动该发布流程。

## 对应现有架构

MuJoCo 世界、裁判和状态推进在 `logic/mujoco/embodied_arena/`；网络与账号管理在其 `platform/` 子包；网页在 `interface/mujoco/`，公开 Python 类型与策略示例在 `CAPI/python/mujoco/`。物理固定步长 0.002 秒，动作周期 0.02 秒，图像周期 0.10 秒，异步收发不修改物理时间。

现有 `logic/logic` 和 `playback/playback` 仍为 .NET 骨架，正式通信 proto 与 Unity 客户端还未提供。本次提供可运行的可选后端、公开接口、回放入口及启动器配置，没有声称完成尚未定义的 gRPC 兼容层。

后续通信组可以把 `CAPI/python/mujoco/api.py` 的公开字段映射到正式消息；逻辑组继续保留单线程固定步长裁判；界面组从只读状态快照与回放读取画面。不要把内部真值坐标、隐藏布局种子、其他队伍的模型或私有日志加入选手消息。

## 本机部署

从仓库根目录运行：

```powershell
dependency/shell/mujoco/deploy.cmd
```

Windows 使用 Python 3.13，虚拟环境在 `logic/mujoco/.venv/`。脚本下载资源时逐文件检查 `assets.lock.json`，第三方文件和模型只保存在忽略目录。默认网页地址为 <http://127.0.0.1:8767>，首次创建管理员后用邀请码注册选手。

## 选手代码与分发包是两种文件

选手上传 ZIP 包含 `submission.json`、`policy.py`、离线权重和辅助模块；通过安全解压、全包 Python 编译与隔离接口检查后，才能练习或报名。清单和机器人适配见 [SUBMISSION_GUIDE.md](SUBMISSION_GUIDE.md)。

下载器分发包包含平台源码、依赖清单、页面、文档和启动配置，通过 `catalog.json` 的大小及 SHA-256 校验更新。它不包含选手的私人提交、账号库、运行结果、`.venv` 或 `.thuai10-state.json`。

生成与发布：

```powershell
python dependency/shell/mujoco/build_package.py logic/mujoco/artifacts/package-v0.4.0
```

将输出目录的 `catalog.json` 与 `payload/` 一起发布到同一 HTTPS 路径。清单的 URL 为 `payload/` 加文件相对路径，安装位置仍使用 `path` 字段。服务器支持 HTTP Range 时，现有下载器可以续传；没有配置正式下载域名时，只生成并验证包，不声称已上线云端下载。

## 提交与审核

从组织 `dev` 创建功能分支，在个人 Fork 推送，用 `type: content` 提交信息向组织 `dev` 提 PR；按贡献指南等待至少一名成员 review。根目录分工、原有忽略规则、许可和 .NET 检查保留。
