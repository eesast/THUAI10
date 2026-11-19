# THUAI10 平台第一版

该版本提供 .NET 10 + Avalonia 桌面窗口，包含文件清单检查、按 SHA-256 增量下载、暂停后按字节续传、本地 Markdown 阅读和配置驱动的本地启动。THUAI9 `dev` 分支的云函数文件清单、保护本地修改和启动脚本是设计参考；这里没有复制其下载器源码。

## 运行

安装 .NET 10 SDK，在仓库根目录执行：

```powershell
dotnet run --project installer/installer/installer.csproj
```

选手包发布后，在“下载与更新”页输入 `catalog.json` 的 HTTPS 地址，选择安装目录，点击“检查更新”和“下载 / 继续”。本机测试允许 localhost HTTP。程序将已下载的部分保存在目标文件旁的 `.part` 文件中；暂停后需重新检查更新，再点“下载 / 继续”。已下载且通过 SHA-256 校验的文件无需重下。

如果本地文件与上次安装记录不同，程序会把它视作选手修改，跳过覆盖。远端清单删除的文件也不会自动删除本地副本。安装记录保存在选手包根目录的 `.thuai10-state.json` 中；发布包不能包含这个文件。

## 发布文件清单

把最终选手包文件放在一个目录中，然后生成清单：

```powershell
dotnet run --project installer/catalog-tool/catalog-tool.csproj -- <选手包目录> <输出的catalog.json> <版本号>
```

把 `catalog.json` 与选手包目录内容上传到同一 HTTPS 路径，使清单中的相对 `url` 能访问对应文件。不要把目录中的用户代码、密钥或本机安装记录上传。服务端需要支持 HTTP Range，才能按字节续传；若不支持，客户端会安全地从头下载该文件。

清单结构：

```json
{
  "version": "0.1.0",
  "files": [
    {
      "path": "docs/README.md",
      "url": "docs/README.md",
      "size": 123,
      "sha256": "64位十六进制SHA-256"
    }
  ]
}
```

## 文档与启动

文档页读取安装目录 `docs/` 下的 Markdown 文件，渲染标题、列表、表格和代码块，支持切换与当前文档关键词计数。图片路径以当前文档为基准；正式文档到位后仍需人工检查图片和站内链接。

启动页读取安装目录中的 `thuai10-launch.json`。这个文件需要逻辑组、通信组和界面组提供最终程序名称、参数和就绪条件后填写。例如：

```json
{
  "port": 8888,
  "readyTimeoutSeconds": 30,
  "server": {
    "path": "logic/Server/Server.exe",
    "arguments": ["--port", "{port}"]
  },
  "interface": {
    "path": "interface/Client.exe",
    "arguments": ["--port", "{port}"]
  },
  "players": [
    {
      "path": "CAPI/cpp/API.exe",
      "arguments": ["-P", "{port}", "-t", "1"]
    }
  ]
}
```

例子中的文件名和参数仅演示格式，**不是 THUAI10 已确定的接口**。启动器先检查本机端口，启动服务器，等待本机端口可连接，再启动界面和选手程序；“停止全部”只结束本次由启动器创建的进程。

## 当前待对接

- 选手包最终文件表、下载域名和云端发布流水线。
- 各组程序的实际路径、启动参数、服务器就绪方式和 macOS 构建产物。
- 正式文档来源、富文本渲染，以及登录、天梯数据接口。

这些接口尚未确定，所以当前版本可用本机测试清单验证下载链路，但不能宣称已经能下载或启动正式 THUAI10 对局。

## 验证

```powershell
dotnet build installer/installer.slnx -c Release
dotnet run --project installer/installer.Tests/installer.Tests.csproj -c Release
```
