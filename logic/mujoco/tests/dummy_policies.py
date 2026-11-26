import time


class Echo:
    def __init__(self, player_id=0, config=None):
        pass

    def act(self, observation):
        return {"joint_targets": observation["q"], "fire": False}


class Failing(Echo):
    def act(self, observation):
        raise RuntimeError("intentional validation failure")


class Slow(Echo):
    def act(self, observation):
        time.sleep(0.2)
        return {"joint_targets": observation["q"], "fire": True}
