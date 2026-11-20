# MuJoCo 源码选手包与启动器

`thuai10-launch.json` 使用现有 `LaunchService` 支持的字段，默认端口 8767。服务器是包内创建的 Python 可执行文件，网页由服务器提供并自动打开，选手通过网页上传策略，因此 `players` 为空。

## 初始化后交给现有启动器

1. 下载或解压生成的选手包。
2. 安装 Python 3.13 和 Docker Desktop Linux 引擎。
3. 在包根目录运行 `dependency/shell/mujoco/setup.cmd`。
4. 运行 `dependency/shell/mujoco/configure-runtime.cmd`，完成镜像与真实通信自检。
5. 用现有 .NET 启动器选择包根目录，点击启动；停止操作只结束启动器创建的进程。

如果直接使用 `deploy.cmd`，它会自己启动后台服务；此时不应再让 .NET 启动器占用同一端口。需要修改端口时同时更新 `thuai10-launch.json`。

## 发布清单

```powershell
python dependency/shell/mujoco/build_package.py logic/mujoco/artifacts/package-v0.4.0
```

生成的 `catalog.json` 使用现有 `PackageCatalog` / `PackageFile` 字段，文件 URL 指向同一发布目录下的 `payload/`。将整个输出目录发布到 HTTPS 后，下载器填写清单 URL 即可读取。代码和本地校验工具不包含正式下载服务器的凭据，也不会修改现有发布地址。

此原型包不包含 Python、Docker 或虚拟环境，不是现成的免安装二进制。现有 `catalog-tool` 仍可对 `payload/` 生成路径、大小和 SHA-256 清单；本工具仅为资源 URL 增加 `payload/` 前缀。
