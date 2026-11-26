# 选手提交与 G1 机器人适配指南

本指南也包含在平台下载的参赛 ZIP 模板中。当前机器人固定为 **Unitree G1，29 个关节，关节位置控制**。参赛者提交视觉、运动控制和决策代码；平台负责 MuJoCo 世界、传感器、物理推进和裁判。

## 从模板开始

```text
submission.zip
├── submission.json        入口、环境与机器人声明
├── policy.py              Policy 类
├── robot.json             平台公开的本体和控制参数，仅供阅读
├── README.md              本说明
├── models/                离线权重
└── src/                   可选的辅助 Python 模块
```

支持 ZIP 多包一层目录，平台会自动规范化并解压。不要放虚拟环境、服务器场景、训练数据集或安装脚本。ZIP 最多 128 MB，解压后最多 512 MB，最多 2048 个文件；包内 Python 源文件编译总量上限 16 MB。每次上传产生新版本，修改后重新上传。

```json
{
  "name": "我的搜索策略",
  "api_version": 1,
  "entry_point": "policy:Policy",
  "environment": "arena-python-v1",
  "robot_id": "unitree_g1_29dof",
  "control_mode": "joint_position",
  "joint_unit": "rad"
}
```

旧版模板未填写机器人字段时，按当前统一 G1 接口解释。声明了其他机器人、角度单位或控制模式时直接拒绝，不会猜测转换。

## Python 入口

```python
from pathlib import Path

ROOT = Path(__file__).resolve().parent

class Policy:
    def __init__(self, player_id=0, config=None):
        self.player_id = player_id
        self.config = config or {}
        self.last_reset = None
        # 例如：在这里从 ROOT / "models" / "actor.onnx" 加载权重。

    def act(self, observation):
        if self.last_reset != observation["reset_count"]:
            self.last_reset = observation["reset_count"]
            # 重置运动控制历史、步态或视觉缓存。
        return {
            "joint_targets": observation["proprio"]["q"].copy(),
            "fire": False,
        }
```

这是通信示例，不能保证站立、行走或完成搜索任务。平台没有通过这个模板给选手自动添加行走控制器。`act` 是同步函数，必须返回字典；不要在里面启动新的 MuJoCo 世界或推进平台仿真。

## 把已有运控模型适配到本体

1. 核对本体。G1 的 12、23、29 关节策略不能仅靠改数组长度互换。模型需要控制同一套关节，使用本平台的关节范围、惯性和执行器设置。
2. 核对状态预处理。姿态四元数为 `w,x,y,z`，角速度的坐标约定见平台接口；角度 rad、角速度 rad/s。观测不是你的训练框架的原始状态向量，需要自行拼接、缩放与维护历史。
3. 核对动作含义。平台需要 **绝对关节位置目标**，单位 rad。模型若输出归一化动作或相对角度，需要在策略内完成 `home + scale * action` 等还原；不能把模型的力矩、速度或 `[-1,1]` 动作直接当成目标角度。
4. 核对关节顺序。默认输出必须与每次观测的 `proprio.joint_names` 一一对应；不要按中文名称、字母序或训练框架索引自行猜测。
5. 先用房间练习检查，再进入城市。接口通过只说明能正确通信；倒地、碰撞和运控性能需要实际观察回放。

模板内 `robot.json` 提供 29 个关节名称、初始参考姿态、公开 PD 参数及 50 Hz 控制／10 Hz 图像频率。平台执行器参数统一固定，策略不能自行修改。

### 已有模型的 29 关节输出顺序不同

可以在 `submission.json` 增加 `action_joint_names`，完整列出**模型输出向量的顺序**：

```python
# 生成清单的示例：training_names 必须是全部 29 个 G1 关节名称，不能重复。
manifest["action_joint_names"] = training_names
```

平台会按名称将 `joint_targets` 从这个顺序重排到实际机器人顺序。它不会修改状态输入顺序、猜测动作尺度或自动补齐 12 关节模型缺失的上半身控制。只有清单不填写该字段时，动作直接按观测顺序处理。

也可完全在策略内按名称组织动作：

```python
targets_by_name = dict(zip(training_names, model_targets, strict=True))
joint_targets = [targets_by_name[name]
                 for name in observation["proprio"]["joint_names"]]
# 这种情况下不再填写 action_joint_names，避免重复重排。
```

## 视觉与模型依赖

- `visual.rgb` 是 uint8、H×W×3、RGB；深度 `visual.depth` 是 H×W、沿光轴的米制深度。模型的缩放、归一化、HWC/NCHW 转换由策略负责。
- 图像 10 Hz，动作 50 Hz。使用 `visual.time` 判断新帧，慢速识别应缓存结果，运动控制继续生成动作。
- 任务包含公共及自己的任务，不提供目标真值位置、隐藏种子或对方私人任务。脚部接触是指示信息，不是触觉阵列。
- 当前环境为 Python 3.13、NumPy 2.5.5、Pillow 13.0.0、ONNX Runtime 1.32.0，**CPU 推理**。没有默认提供 PyTorch、OpenCV 或 CUDA。
- 所有权重随包上传，使用 `Path(__file__)` 拼接相对路径。运行时禁外网，不能临时安装依赖或下载权重。
- 不接受让平台执行任意 `setup.sh`／`pip install`。需要额外库时在网页提交申请；源代码 C/C++ 编译器不是统一环境的一部分。

## 上传之后平台检查什么

1. 保存 ZIP 与摘要，生成不可覆盖的版本号。
2. 检查路径、大小、压缩率、重复文件和链接，规范化一层目录后自动解压。
3. 检查 JSON、固定入口、机器人、动作模式、弧度单位和声明的关节名称，并静态解析入口语法。
4. 在隔离容器内**编译包内全部 Python 文件**，包括未被 `policy.py` 导入的辅助模块。编译不执行模块；语法错误会显示相对文件名和行号。
5. 在两个独立实例中真正导入并初始化 `Policy`，随后用实际 RGB-D 观测调用三次 `act`，验证 29 个有限目标角度及布尔 `fire`。
6. 通过后可以练习或报名；勾选“检查通过后自动开始城市练习”时，平台会继续排队仿真，再把真实成绩、事件与回放返回网页。

接口检查不能保证模型效果，不能证明所有执行分支正确，也不保证机器人保持平衡。

## 常见问题

| 页面报告 | 处理办法 |
| --- | --- |
| 找不到 policy.py | 与 submission.json 放在同一根目录；允许多包一层目录 |
| 机器人／控制模式不匹配 | 使用当前 G1 29 关节位置接口，核对训练本体与动作含义 |
| action_joint_names 不完整 | 声明全部 29 个唯一关节名称，或在策略内自己按名称重排 |
| Python 编译失败 | 根据报错文件与行号修复，包括 src 下的辅助模块 |
| 返回 28／12 个关节 | 返回完整 29 个目标；不足的控制需要选手显式实现 |
| ImportError 或模型找不到 | 核对统一依赖及 models 内路径，不要引用自己电脑的绝对路径 |
| NaN／无穷值／fire 类型错误 | 清理模型输出，fire 使用 True/False |
| 初始化／推理超时 | 检查模型大小和 CPU 用时；缓存视觉结果，避免阻塞运控 |
| 等待执行环境 | 让管理员点击“运行环境 → 一键部署并自检”，原队列会继续 |

初始化默认限时 90 秒，单次响应 1 秒；每份策略 1 核 CPU／1024 MB 内存，整局实际时间上限 900 秒。超时、无效动作、开火冷却与倒地判罚以平台公布规则为准。

## 练习、正式比赛和模型训练

练习是运行你的策略并评测，返回成绩与轨迹，不会自动优化模型参数或生成新权重。正式比赛使用已锁定版本，由管理员安排对手、固定配置并发布结果。

如果需要强化学习或其他模型训练，应先在独立训练环境里完成训练，再将推理策略和权重提交。当前平台没有提供自动优化模型参数的训练循环，不能把一次自测结果当作新模型。

练习、代码、权重和私有日志仅本人及管理员可见；正式成绩和回放发布后对平台内选手开放。详细观测字段见网页“接口与环境”与仓库 `docs/INTERFACE.md`。


## v0.4 入门包与多环境

网页的「入门行走包」含 Holosoma 29-DoF ONNX 权重、许可、机器人参数、简单深度避障和 `starter.json`。前 2 秒站立，此后按 speed 前进；设为 0 可测试站立。它不包含完整搜索、瞄准、自主起身或交通安全保证。通过房间练习后再调试城市。

管理员发布后，可在清单中选择 `arena-torch-cpu-v1` 或 `arena-cuda-v1`。CPU PyTorch 固定 2.7.0；CUDA 为 cu128 与 ONNX Runtime GPU 1.32.0。额外环境必须使用相应页面下载的模板，或手动修改清单；双方环境一致才能比赛。

ONNX GPU 策略应显式指定 `providers=['CUDAExecutionProvider']` 并检查实际 provider；PyTorch 使用 `torch.cuda.is_available()` 检查并将模型与输入转到同一设备。平台不会将模型自动搬到 GPU，也不会自动转换权重。GPU 设备未验收时不可选择该环境。

新版城市任务 `mixed-v1` 含五类物品及同色异形干扰物；以任务文字与参考图共同匹配，不能只按颜色开火。交换出生位置的正式比赛同时交换私人任务组。仍只返回自己的任务，不提供世界真值。

练习结束后使用「运行诊断」查看平均、95 分位和最大响应耗时、生命与耗时曲线、失误和碰撞计数。可在练习页比较两个版本；不同布局的单次分数不代表稳定排名，应看多局赛事总榜。
