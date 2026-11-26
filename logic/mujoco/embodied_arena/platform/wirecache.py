"""Lossless transport cache: images stay at 10 Hz while joint control stays at 50 Hz."""


class ObservationCache:
    def __init__(self):
        self.visual_time = None
        self.tasks = None

    def prepare(self, message):
        if message.get("op") != "act":
            return message, (self.visual_time, self.tasks)
        original = message["observation"]
        observation = dict(original)
        packet = {**message, "observation": observation}
        visual = original.get("visual")
        stamp = visual["time"] if visual is not None else None
        tasks = tuple(t["id"] for t in original.get("tasks", []))
        if visual is not None and self.visual_time == stamp:
            packet["reuse_visual"] = True
            observation.pop("visual", None)
        if self.tasks == tasks:
            packet["reuse_tasks"] = True
            observation.pop("tasks", None)
        return packet, (stamp, tasks)

    def commit(self, state):
        self.visual_time, self.tasks = state
