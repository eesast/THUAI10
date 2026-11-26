# MuJoCo 部署与验证工具

从仓库根目录调用，脚本会定位 `logic/mujoco/`，无需修改全局 Python 路径。

| 工具 | 作用 |
| --- | --- |
| `deploy.cmd` | 安装、资源校验、实际通信自检并启动网页 |
| `setup.cmd` | 仅创建环境、安装依赖和获取资源 |
| `configure-runtime.cmd` | 准备 Docker 执行环境，不启动网页 |
| `start.cmd` | 日常后台启动网页，默认 8767 端口 |
| `fetch_assets.py` | 固定提交和逐文件 SHA-256 校验 |
| `build_package.py` | 生成下载器清单、白名单分发文件和源码 ZIP |
| `validate_platform.py` | 真实 Docker / MuJoCo / 权限闭环验收 |
| `validate_release.py` | 完整 60 秒城市和循环赛验收 |
| `restore_platform.py` | 将完整快照恢复到全新目录 |

生成数据放在 `logic/mujoco/var/` 和 `logic/mujoco/artifacts/`，不要提交。日常服务不包含预设密码；测试服务只能使用独立目录，测试账号不是生产账号。
