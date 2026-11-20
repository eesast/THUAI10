# MuJoCo Python 选手接口

`api.py` 定义当前原型公开的观测与动作类型；`policy.py` 是随下载包分发的 G1 29 关节行走示例。类型与示例由平台下载入口直接读取，避免维护两份不同的接口。

选手从网页下载模板后会获得机器人参数、类型文件、说明和离线权重。不要直接在本目录运行策略；仓库不提交模型，下载模板中的 `models/walk.onnx` 和许可由校验后的资源生成。

```python
class Policy:
    def __init__(self, player_id=0, config=None):
        self.player_id = player_id

    def act(self, observation):
        return {
            "joint_targets": observation["proprio"]["q"].copy(),
            "fire": False,
        }
```

上述最小示例只验证输入输出。完整行走示例和关节适配说明见平台下载包及 [提交指南](../../../docs/mujoco/SUBMISSION_GUIDE.md)。当前传输为受限 JSON / 数值数组，并非尚未定义的正式 Protobuf / gRPC 接口。
