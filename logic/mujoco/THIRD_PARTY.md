# 开源资源与改动记录

下载内容保留在 `third_party/`，不修改上游原件。版本、逐文件 URL 和 SHA-256 见 `assets.lock.json`；下载后的对应清单见 `third_party/manifest.json`。

## MuJoCo Menagerie / Unitree G1

- 来源：https://github.com/google-deepmind/mujoco_menagerie/tree/370c43965323c0944b433b202aac5058b5f907a9/unitree_g1
- 版本：`370c43965323c0944b433b202aac5058b5f907a9`。
- 许可：G1 目录 BSD-3-Clause，原文保留为 `third_party/g1/LICENSE`。
- 使用：`g1.xml`、对应 STL、说明和许可证。
- 改动通过运行时场景构建完成：复制两台机器人并给名称加前缀；加入摄像头、手持仿真枪和枪口 site；设置公开执行器参数与初始姿态；把模型与场景组合。上游文件不覆盖。

## Amazon FAR Holosoma

- 来源：https://github.com/amazon-far/holosoma/tree/78aeb23ed478de980c43e979f5e70be1b9699187
- 版本：`78aeb23ed478de980c43e979f5e70be1b9699187`。
- 许可：Apache-2.0，原文保留为 `third_party/holosoma/LICENSE`。上游独立第三方资源仍遵循各自许可。
- 使用：G1 29-DoF FastSAC ONNX 行走权重、部署配置及参考代码。默认动作尺度 0.25；观测项按上游构建器的字母顺序排列。关节名字和 PD 参数来自模型元数据。
- 本项目自行实现适配器与视觉验收程序；未使用上游真实机器人通信与部署模块。
- 经过本地静止、前进和双机器人视觉任务验证。尚未验证所有姿态、碰撞、复杂地形、自主起身或实机能力。

## Unitree RL Gym

- 来源：https://github.com/unitreerobotics/unitree_rl_gym/tree/276801e46c5d433564f24658bac64f254b7d2d4b
- 版本：`276801e46c5d433564f24658bac64f254b7d2d4b`。
- 许可：BSD-3-Clause，原文保留为 `third_party/unitree_rl_gym/LICENSE`。
- 使用：G1 `motion.pt` 预训练权重、配置和部署参考，用于调研和 12 关节策略转移比较。
- 适配器中的观测尺度、步态相位与动作还原方式参考上游部署程序。当前未将此 12 关节策略用于默认比赛。

## Orbitron 开放字体

- 来源：https://github.com/google/fonts/tree/8b0a1d0f5983c89bc2b93f1b5fb55f9e252744b5/ofl/orbitron
- 作者：The Orbitron Project Authors，保留字体名称 Orbitron。
- 许可：SIL Open Font License 1.1，原文保留为 `third_party/orbitron/OFL.txt`。
- 使用：城市招牌与街幕的字形。没有修改字体文件，程序生成的标牌图像位于 `assets/cyber_city`。

## 城市场景

街区建筑、悬浮车、巡逻角色、家具、植物与贴图由本项目的程序化场景代码生成。G1 参赛本体继续使用上述 Menagerie 模型；没有将其他来源未明的城市模型打包进项目。

## Python 运行依赖

MuJoCo、NumPy、Pillow、ONNX Runtime 等依赖各自保留许可；安装版本见 [固定依赖](../../dependency/python/mujoco/requirements-lock.txt)。本地调研安装了 PyTorch，用于验证 Unitree TorchScript 权重，默认 Holosoma 演示不依赖 PyTorch。

本项目未获得上述组织的背书。当前所有验证均为仿真验证。


## 本模块许可

迁入 THUAI10 的自有代码遵循仓库根目录 MIT 许可，第三方模型、字体和依赖仍保留上述各自许可。下载的模型和许可证由资源工具校验，不提交到源码仓库。
