# MuJoCo 轨迹回放

```powershell
logic/mujoco/.venv/Scripts/python.exe playback/mujoco/replay.py <轨迹目录>
```

读取已保存状态、动作、动态背景和事件，不执行选手代码。网页也可查看经过权限检查的真实多视角图片回放。本入口与现有 .NET `playback` 工程并存；正式 `.thuaipb` 格式尚未定义，本次不声明两种格式互通。
