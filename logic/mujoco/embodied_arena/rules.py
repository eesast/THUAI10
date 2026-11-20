"""Deterministic game rules; simultaneous shots use a pre-event eligibility snapshot."""

from dataclasses import dataclass

from .config import MatchConfig


@dataclass
class Player:
    health: float
    score: float = 0.0
    disabled_until: float = 0.0
    next_shot: float = 0.0
    respawn_at: float | None = None
    down_since: float | None = None
    upright_since: float | None = None


@dataclass
class Target:
    id: str
    owner: int | None
    points: float
    active: bool = True


@dataclass(frozen=True)
class Hit:
    kind: str  # player, target, miss
    id: int | str | None = None


class Referee:
    def __init__(self, config: MatchConfig, targets: list[Target], count: int = 2):
        self.config = config
        self.players = [Player(config.health) for _ in range(count)]
        self.targets = {target.id: target for target in targets}
        self.events: list[dict] = []
        self.hazard_last_contact: dict[tuple[int, str], float] = {}

    def event(self, now: float, kind: str, **fields):
        self.events.append({"time": round(now, 6), "type": kind, **fields})

    def can_fire(self, player: int, now: float) -> bool:
        p = self.players[player]
        return (
            p.respawn_at is None
            and p.health > 0
            and now + 1e-9 >= max(p.next_shot, p.disabled_until)
        )

    def resolve_shots(self, now: float, shots: dict[int, Hit]):
        accepted = {pid: hit for pid, hit in shots.items() if self.can_fire(pid, now)}
        alive = {i for i, p in enumerate(self.players) if p.respawn_at is None and p.health > 0}
        damages = [0.0] * len(self.players)
        completions: dict[str, list[int]] = {}
        for pid, hit in sorted(accepted.items()):
            self.players[pid].next_shot = now + self.config.shot_cooldown
            if hit.kind == "player" and hit.id in alive and hit.id != pid:
                other = int(hit.id)
                damages[other] += self.config.hit_damage
                self.players[other].disabled_until = max(
                    self.players[other].disabled_until, now + self.config.stun_seconds
                )
                self.event(now, "player_hit", player=pid, victim=other)
            elif hit.kind == "target" and str(hit.id) in self.targets:
                target = self.targets[str(hit.id)]
                if target.active and target.owner in (None, pid):
                    completions.setdefault(target.id, []).append(pid)
                    continue
                damages[pid] += self.config.miss_damage
                self.event(now, "miss", player=pid, reason="invalid_target")
            else:
                damages[pid] += self.config.miss_damage
                self.event(now, "miss", player=pid, reason="no_valid_hit")
        for target_id, winners in completions.items():
            target = self.targets[target_id]
            target.active = False
            for pid in winners:
                points = target.points / len(winners)
                self.players[pid].score += points
                self.event(now, "target_completed", player=pid, target=target_id, points=points)
        for pid, damage in enumerate(damages):
            self.damage(pid, damage, now, "shot")

    def damage(self, pid, amount, now, cause):
        p = self.players[pid]
        if p.respawn_at is not None or p.health <= 0:
            return
        p.health = max(0.0, p.health - amount)
        if p.health == 0:
            p.respawn_at = now + self.config.respawn_delay
            p.down_since = p.upright_since = None
            self.event(now, "death", player=pid, cause=cause)

    def traffic_contact(self, pid, vehicle, now, force, speed):
        p = self.players[pid]
        if p.respawn_at is not None or p.health <= 0 or force < self.config.traffic_min_force:
            return False
        key = (pid, vehicle)
        if (
            now - self.hazard_last_contact.get(key, -1e9) + 1e-9
            < self.config.traffic_contact_cooldown
        ):
            return False
        self.hazard_last_contact[key] = now
        self.event(
            now,
            "traffic_collision",
            player=pid,
            vehicle=vehicle,
            damage=self.config.traffic_damage,
            force=round(force, 3),
            vehicle_speed=speed,
        )
        self.damage(pid, self.config.traffic_damage, now, "traffic")
        return True

    def tick(self, now: float, postures: list[str]) -> list[int]:
        reset = []
        for pid, (p, posture) in enumerate(zip(self.players, postures, strict=True)):
            if p.respawn_at is not None:
                if now + 1e-9 >= p.respawn_at:
                    p.health = self.config.health
                    p.respawn_at = None
                    p.disabled_until = p.next_shot = now
                    p.down_since = p.upright_since = None
                    reset.append(pid)
                    self.event(now, "respawn", player=pid)
                continue
            if posture == "down" and p.down_since is None:
                p.down_since = now
                self.event(now, "fall", player=pid)
            if p.down_since is None:
                continue
            if posture == "upright":
                if p.upright_since is None:
                    p.upright_since = now
                if now - p.upright_since + 1e-9 >= self.config.upright_hold:
                    p.down_since = p.upright_since = None
                    self.event(now, "self_recovery", player=pid)
                    continue
            else:
                p.upright_since = None
            if now - p.down_since + 1e-9 >= self.config.fall_timeout:
                p.down_since = p.upright_since = None
                reset.append(pid)
                self.event(now, "fall_reset", player=pid)
        return reset
