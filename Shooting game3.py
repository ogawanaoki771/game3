# ============================================================
# LAW OF CHANGE : TRANSFORMATION AI
#
# YOU + AI-A + AI-B
#
# NO Q-LEARNING
# NO REWARD
# NO Q-VALUE
# NO EXPERIENCE REPLAY
#
# AI = OBSERVE -> PREDICT -> COMPARE -> LEARN CHANGE -> ACT
#
# The AI does not learn "which action is worth more".
# It learns recurring transformations of the world.
#
# Controls
#   A/D or Left/Right : move
#   W/S or Up/Down    : aim
#   SPACE             : shoot
#   SHIFT             : dash
#   R                 : reset fighters
#   E                 : erase persistent laws/memory
#   P                 : pause
# ============================================================

import math
import json
import random
import turtle
from collections import defaultdict, deque

# ------------------------------------------------------------
# CONFIG
# ------------------------------------------------------------
W, H = 1200, 780
LEFT, RIGHT = -560, 560
BOTTOM, TOP = -300, 250
FPS_MS = 28

PLAYER_R = 16
MOVE = 1.10
DASH = 7.2
BULLET_SPEED = 13.0
BULLET_LIFE = 78
MAX_HP = 100.0

MEMORY_FILE = "law_transform_memory.json"

COLORS = ["#00eaff", "#57ff9b", "#ff9f43"]
NAMES = ["YOU", "AI-A", "AI-B"]

ACTIONS = ("APPROACH", "RETREAT", "STRAFE", "HOLD", "DASH", "SHOOT")

ASSIST_STRENGTH = 0.28
AUTOPILOT_DELAY = 12
AUTOPILOT_STRENGTH = 0.78

# ------------------------------------------------------------
# UTILS
# ------------------------------------------------------------
def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def angle_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def quantize(v, step):
    return int(round(v / step))


# ------------------------------------------------------------
# PERSISTENT LAW
# ------------------------------------------------------------
class LawMemory:
    """The world slowly accumulates visible traces of recurring changes."""

    def __init__(self):
        self.laws = []
        self.load()

    def remember(self, x, y, kind, strength=0.10):
        for law in self.laws:
            if law["kind"] == kind and distance(x, y, law["x"], law["y"]) < 85:
                law["x"] = law["x"] * 0.88 + x * 0.12
                law["y"] = law["y"] * 0.88 + y * 0.12
                law["strength"] = min(1.0, law["strength"] + strength)
                law["hits"] += 1
                return

        self.laws.append({
            "x": float(x),
            "y": float(y),
            "kind": str(kind),
            "strength": float(strength),
            "hits": 1,
        })

        if len(self.laws) > 160:
            self.laws.sort(key=lambda z: z["strength"])
            self.laws.pop(0)

    def influence(self, x, y):
        fx = fy = 0.0
        for law in self.laws:
            d = distance(x, y, law["x"], law["y"])
            if d > 140:
                continue

            w = law["strength"] * (1.0 - d / 140.0)
            kind = law["kind"]

            if kind == "HIT":
                fx += math.sin((x - law["x"]) * 0.06) * 0.05 * w
            elif kind == "BOUNCE":
                fy += math.copysign(0.06 * w, y - law["y"] or 1)
            elif kind == "DASH":
                fx += 0.07 * w
            elif kind == "MISS":
                fy -= 0.035 * w
            elif kind == "COLLISION":
                fx += (law["x"] - x) * 0.0008 * w
                fy += (law["y"] - y) * 0.0008 * w

        return fx, fy

    def decay(self):
        for law in self.laws:
            law["strength"] *= 0.9990
        self.laws = [x for x in self.laws if x["strength"] > 0.02]

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.laws, f, ensure_ascii=False, indent=2)
        except OSError:
            pass

    def load(self):
        try:
            with open(MEMORY_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            self.laws = [x for x in data if isinstance(x, dict)]
        except (OSError, json.JSONDecodeError, TypeError, ValueError):
            self.laws = []


# ------------------------------------------------------------
# TRANSFORMATION GRAPH
# ------------------------------------------------------------
class TransformationGraph:
    """Stores recurring transitions between events, not action values."""

    def __init__(self):
        self.edges = defaultdict(int)
        self.last_event = {}
        self.event_count = defaultdict(int)

    def observe(self, fighter_id, event):
        previous = self.last_event.get(fighter_id)
        self.event_count[event] += 1

        if previous is not None and previous != event:
            self.edges[(previous, event)] += 1

        self.last_event[fighter_id] = event

    def transition_strength(self, a, b):
        return self.edges.get((a, b), 0)

    def predicted_next(self, event, limit=4):
        candidates = []
        for (a, b), count in self.edges.items():
            if a == event:
                candidates.append((count, b))
        candidates.sort(reverse=True)
        return candidates[:limit]

    def count(self):
        return len(self.edges)


# ------------------------------------------------------------
# CHANGE MEMORY
# ------------------------------------------------------------
class ChangeMemory:
    """Learns recurring transformations and prediction error.

    There is intentionally no reward, no Q table and no replay buffer.
    """

    def __init__(self):
        self.state_history = deque(maxlen=80)
        self.change_history = deque(maxlen=120)
        self.transition_counts = defaultdict(int)
        self.context_changes = defaultdict(lambda: defaultdict(int))
        self.prediction_error = 0.0
        self.curiosity = 1.0
        self.last_prediction = None
        self.last_state = None
        self.last_change = None
        self.learn_steps = 0

    def encode_state(self, me, target, world):
        if target is None:
            return (
                quantize(me.x, 80),
                quantize(me.y, 70),
                quantize(me.vx, 2),
                quantize(me.vy, 2),
                int(me.hp // 20),
                int(world.zone > 0.5),
            )

        d = distance(me.x, me.y, target.x, target.y)
        return (
            clamp(quantize(target.x - me.x, 80), -8, 8),
            clamp(quantize(target.y - me.y, 70), -6, 6),
            clamp(quantize(target.vx - me.vx, 2.5), -5, 5),
            clamp(quantize(target.vy - me.vy, 2.5), -5, 5),
            int(me.hp // 20),
            int(target.hp // 20),
            int(d // 150),
            int(world.zone > 0.5),
        )

    def encode_change(self, me, target, old_state, event):
        if old_state is None:
            return (event, "INIT")

        speed = math.hypot(me.vx, me.vy)
        dx = me.x - (target.x if target else me.x)
        dy = me.y - (target.y if target else me.y)

        motion = "STILL"
        if speed > 5.0:
            motion = "FAST"
        elif speed > 1.5:
            motion = "MOVE"

        side = "CENTER"
        if target is not None:
            rel = dx * target.vy - dy * target.vx
            if rel > 30:
                side = "LEFT_ORBIT"
            elif rel < -30:
                side = "RIGHT_ORBIT"

        return (
            event,
            motion,
            side,
            int(me.hp // 25),
        )

    def predict_change(self, state):
        candidates = self.context_changes.get(state)
        if not candidates:
            return None, 0

        best = max(candidates.items(), key=lambda p: p[1])
        return best[0], best[1]

    def observe(self, me, target, world, event):
        state = self.encode_state(me, target, world)
        change = self.encode_change(me, target, self.last_state, event)

        predicted, strength = self.predict_change(state)
        if predicted is not None:
            if predicted != change:
                self.prediction_error = 0.96 * self.prediction_error + 0.04
            else:
                self.prediction_error = 0.96 * self.prediction_error

        if self.last_change is not None:
            self.transition_counts[(self.last_change, change)] += 1

        self.context_changes[state][change] += 1
        self.state_history.append(state)
        self.change_history.append(change)
        self.last_state = state
        self.last_change = change
        self.last_prediction = predicted
        self.curiosity = clamp(
            0.65 * self.prediction_error
            + 0.35 / math.sqrt(1 + len(self.change_history)),
            0.03,
            1.0,
        )
        self.learn_steps += 1

    def predict_from_recent(self, state):
        predicted, count = self.predict_change(state)
        if predicted is None:
            return None, 0.0
        total = sum(self.context_changes[state].values())
        confidence = count / max(1, total)
        return predicted, confidence

    def transition_score(self, old_change, candidate_change):
        if old_change is None:
            return 0.0
        count = self.transition_counts.get((old_change, candidate_change), 0)
        return math.log1p(count)


# ------------------------------------------------------------
# OPPONENT MODEL
# ------------------------------------------------------------
class OpponentModel:
    def __init__(self):
        self.data = defaultdict(lambda: {
            "left": 0.0,
            "right": 0.0,
            "turn": 0.0,
            "last_x": None,
            "last_y": None,
            "last_vx": 0.0,
            "last_vy": 0.0,
        })

    def observe(self, enemy):
        d = self.data[enemy.pid]
        if d["last_x"] is not None:
            dx = enemy.x - d["last_x"]
            dy = enemy.y - d["last_y"]

            if abs(dx) > abs(dy):
                d["right" if dx > 0 else "left"] += 1.0

            if abs(dx * d["last_vy"] - dy * d["last_vx"]) > 10:
                d["turn"] += 0.5

        d["last_x"] = enemy.x
        d["last_y"] = enemy.y
        d["last_vx"] = enemy.vx
        d["last_vy"] = enemy.vy

    def dodge_bias(self, enemy_pid):
        d = self.data[enemy_pid]
        total = d["left"] + d["right"] + 1.0
        return (d["right"] - d["left"]) / total


# ------------------------------------------------------------
# TRANSFORMATION AI
# ------------------------------------------------------------
class TransformationAI:
    """Chooses actions from predicted transformations and geometry.

    No reward is produced. No action value is stored.
    """

    def __init__(self, pid, style):
        self.pid = pid
        self.style = style
        self.memory = ChangeMemory()
        self.opponents = OpponentModel()
        self.transitions = TransformationGraph()
        self.recent_events = deque(maxlen=30)
        self.last_action = "HOLD"
        self.last_event = None

    def observe_all(self, me, fighters, world):
        enemies = [f for f in fighters if f.pid != me.pid and f.alive]
        for enemy in enemies:
            self.opponents.observe(enemy)

        target = min(
            enemies,
            key=lambda e: distance(me.x, me.y, e.x, e.y),
            default=None,
        )

        event = self.current_event(me, target, world)
        self.memory.observe(me, target, world, event)
        self.transitions.observe(me.pid, event)
        self.recent_events.append(event)
        self.last_event = event

    def current_event(self, me, target, world):
        if not me.alive:
            return "BREAK"
        if world.zone > 0.75:
            return "DANGER"
        if target is not None:
            d = distance(me.x, me.y, target.x, target.y)
            if d < 70:
                return "CLOSE"
            if d < 180:
                return "PRESSURE"
            if d > 480:
                return "DISTANT"
        speed = math.hypot(me.vx, me.vy)
        if speed < 0.4:
            return "STILL"
        if speed > 6.5:
            return "FAST"
        return "MOVE"

    def predicted_event(self):
        if not self.recent_events:
            return None, 0.0
        event = self.recent_events[-1]
        candidates = self.transitions.predicted_next(event, limit=3)
        if not candidates:
            return None, 0.0
        count, next_event = candidates[0]
        total = sum(c for (a, _), c in self.transitions.edges.items() if a == event)
        confidence = count / max(1, total)
        return next_event, confidence

    def score_action(self, action, me, target, enemies, world):
        d = distance(me.x, me.y, target.x, target.y) if target else 999.0
        danger = sum(max(0.0, 1.0 - distance(me.x, me.y, e.x, e.y) / 220.0)
                      for e in enemies)
        danger += world.zone * 0.8

        score = 0.0

        # Geometry. This is not reward; it is a direct world constraint.
        if action == "APPROACH":
            score += 0.6 if d > 270 else -0.15
        elif action == "RETREAT":
            score += 0.8 if d < 190 else 0.0
            score += 0.4 * danger
        elif action == "STRAFE":
            score += 0.65 if 120 < d < 420 else 0.1
        elif action == "HOLD":
            score += 0.45 if 180 < d < 340 else -0.05
        elif action == "DASH":
            score += 0.9 if danger > 1.0 else 0.12
        elif action == "SHOOT":
            score += 0.75 if d < 520 else -0.2

        # Body condition.
        if me.hp < 30 and action in ("RETREAT", "DASH"):
            score += 0.65
        if target is not None and target.hp < 35 and action in ("APPROACH", "SHOOT"):
            score += 0.35

        # Style is a bias, not a learned value.
        if self.style == "aggressive" and action in ("APPROACH", "SHOOT"):
            score += 0.18
        elif self.style == "tactical" and action in ("STRAFE", "RETREAT"):
            score += 0.18

        # Predictive transformation principle.
        predicted, confidence = self.predicted_event()
        if predicted is not None:
            if predicted == "CLOSE" and action in ("RETREAT", "DASH", "STRAFE"):
                score += 0.28 * confidence
            elif predicted == "DISTANT" and action == "APPROACH":
                score += 0.22 * confidence
            elif predicted == "PRESSURE" and action == "STRAFE":
                score += 0.20 * confidence
            elif predicted == "DANGER" and action in ("RETREAT", "DASH"):
                score += 0.30 * confidence

        # Curiosity = preference for poorly predicted situations.
        if action in ("STRAFE", "DASH"):
            score += 0.10 * self.memory.curiosity

        # Avoid endless action loops.
        if action == self.last_action:
            score -= 0.025
        if len(self.recent_events) >= 5:
            last5 = list(self.recent_events)[-5:]
            if len(set(last5)) == 1 and action in ("HOLD", "APPROACH"):
                score -= 0.06 * self.memory.curiosity

        return score

    def choose(self, me, target, fighters, world):
        enemies = [f for f in fighters if f.pid != me.pid and f.alive]
        self.observe_all(me, fighters, world)

        scored = [
            (self.score_action(action, me, target, enemies, world), action)
            for action in ACTIONS
        ]
        scored.sort(reverse=True)

        # Exploration is driven by novelty/prediction uncertainty,
        # not epsilon-greedy reward learning.
        top_k = 2 if self.style == "aggressive" else 3
        if random.random() < 0.08 + 0.18 * self.memory.curiosity:
            action = random.choice(scored[:top_k])[1]
        else:
            action = scored[0][1]

        self.last_action = action
        return action

    def predict_position(self, target, horizon):
        if target is None:
            return None

        hist = self.opponents.data[target.pid]
        vx = hist["last_vx"]
        vy = hist["last_vy"]
        bias = self.opponents.dodge_bias(target.pid)
        damp = max(0.45, 1.0 - self.memory.prediction_error * 0.5)

        return (
            target.x + vx * horizon * damp + bias * 2.0 * horizon,
            target.y + vy * horizon * damp,
        )

    def intercept_angle(self, me, target):
        if target is None:
            return me.angle

        best_angle = me.angle
        best_error = 1e9

        for h in (5, 8, 11, 15):
            pred = self.predict_position(target, h)
            if pred is None:
                continue
            px, py = pred
            a = math.atan2(py - me.y, px - me.x)
            ex = me.x + math.cos(a) * BULLET_SPEED * h
            ey = me.y + math.sin(a) * BULLET_SPEED * h
            err = distance(ex, ey, px, py)
            if err < best_error:
                best_error = err
                best_angle = a

        return best_angle


# ------------------------------------------------------------
# BULLET
# ------------------------------------------------------------
class Bullet:
    def __init__(self, owner, x, y, vx, vy):
        self.owner = owner
        self.x = x
        self.y = y
        self.vx = vx
        self.vy = vy
        self.life = BULLET_LIFE


# ------------------------------------------------------------
# WORLD
# ------------------------------------------------------------
class World:
    def __init__(self):
        self.time = 0
        self.zone = 0.0
        self.memory = LawMemory()
        self.graph = TransformationGraph()

    def update(self):
        self.time += 1
        self.zone *= 0.995
        if self.time % 180 == 0:
            self.memory.decay()
        if self.time % 600 == 0:
            self.memory.save()

    def hit_world(self, x, y):
        self.zone = min(1.0, self.zone + 0.032)
        self.memory.remember(x, y, "HIT", 0.05)


# ------------------------------------------------------------
# FIGHTER
# ------------------------------------------------------------
class Fighter:
    def __init__(self, pid, x, y, world, ai=False, style="tactical"):
        self.pid = pid
        self.name = NAMES[pid]
        self.color = COLORS[pid]
        self.world = world
        self.ai = ai
        self.style = style
        self.spawn_x = x
        self.spawn_y = y
        self.brain = TransformationAI(pid, style) if ai else None

        self.body = turtle.Turtle(shape="circle")
        self.body.penup()
        self.body.speed(0)
        self.body.color(self.color)
        self.body.shapesize(1.2, 1.2)
        self.reset()

    def reset(self):
        self.x = self.spawn_x
        self.y = self.spawn_y
        self.vx = 0.0
        self.vy = 0.0
        self.angle = 0.0
        self.hp = MAX_HP
        self.cooldown = 0
        self.dash_cd = 0
        self.alive = True
        self.shots = 0
        self.hits = 0
        self.dashes = 0
        self.last_action = "HOLD"
        self.input_idle = 0
        self.assist_active = False
        self.body.goto(self.x, self.y)

    @property
    def attack_power(self):
        return 1.0 + (1.0 - self.hp / MAX_HP) * 1.55

    @property
    def speed(self):
        return 1.0 + 0.20 * (1.0 - self.hp / MAX_HP)

    def state(self):
        if not self.alive:
            return "BREAK"
        if self.hp < 20:
            return "DANGER"
        if self.hp < 50:
            return "CRITICAL"
        if self.hp < 80:
            return "DAMAGED"
        return "NORMAL"

    def target(self, fighters):
        enemies = [f for f in fighters if f.pid != self.pid and f.alive]
        if not enemies:
            return None

        def score(enemy):
            d = distance(self.x, self.y, enemy.x, enemy.y)
            pressure = enemy.hp * 1.45
            danger = 40 if enemy.hp < 30 else 0
            return d + pressure - danger

        return min(enemies, key=score)

    def control_ai(self, fighters):
        target = self.target(fighters)
        if target is None:
            return 0.0, 0.0, False, False

        action = self.brain.choose(self, target, fighters, self.world)
        self.last_action = action
        self.angle = self.brain.intercept_angle(self, target)

        d = distance(self.x, self.y, target.x, target.y)
        dx = target.x - self.x
        dy = target.y - self.y
        nx = dx / max(1.0, d)
        ny = dy / max(1.0, d)

        side = -1 if math.sin(self.world.time * 0.045 + self.pid * 2.1) < 0 else 1
        sx = -ny * side
        sy = nx * side

        mx = my = 0.0
        shoot = False
        dash = False

        if action == "APPROACH":
            mx, my = nx, ny
        elif action == "RETREAT":
            mx, my = -nx, -ny
        elif action == "STRAFE":
            mx, my = sx + nx * 0.15, sy + ny * 0.15
        elif action == "HOLD":
            if d < 155:
                mx, my = -nx, -ny
            elif d > 330:
                mx, my = nx, ny
        elif action == "DASH":
            dash = self.dash_cd <= 0
            mx, my = ((-nx, -ny) if self.hp < 35 else (sx, sy))
        elif action == "SHOOT":
            mx, my = (nx, ny) if d > 500 else (sx, sy)
            shoot = d < 540

        # Hard geometric safety constraint, independent of learning.
        if self.hp < 24 and d < 210:
            mx, my = -nx, -ny
            dash = self.dash_cd <= 0

        if self.cooldown <= 0 and d < 540:
            shoot = True

        return mx, my, shoot, dash

    def control_user(self, keys, fighters):
        ux = int("right" in keys or "d" in keys) - int("left" in keys or "a" in keys)
        uy = int("up" in keys or "w" in keys) - int("down" in keys or "s" in keys)
        shoot = "shoot" in keys
        dash = "dash" in keys

        has_move_input = bool(ux or uy)

        if has_move_input:
            self.input_idle = 0
            self.assist_active = True

            length = math.hypot(ux, uy)
            ux /= length
            uy /= length

            enemies = [f for f in fighters if f.pid != self.pid and f.alive]
            target = min(
                enemies,
                key=lambda f: distance(self.x, self.y, f.x, f.y),
                default=None,
            )

            ax = ay = 0.0
            if target is not None:
                d = distance(self.x, self.y, target.x, target.y)
                dx = target.x - self.x
                dy = target.y - self.y
                nx = dx / max(1.0, d)
                ny = dy / max(1.0, d)

                if d < 170:
                    ax, ay = -nx, -ny
                elif d > 430:
                    ax, ay = nx, ny
                else:
                    ax, ay = -ny, nx

                fx, fy = self.world.memory.influence(self.x, self.y)
                ax += fx * 2.0
                ay += fy * 2.0

                alen = math.hypot(ax, ay)
                if alen > 0:
                    ax /= alen
                    ay /= alen

            mx = ux * (1.0 - ASSIST_STRENGTH) + ax * ASSIST_STRENGTH
            my = uy * (1.0 - ASSIST_STRENGTH) + ay * ASSIST_STRENGTH

            if mx or my:
                self.angle = math.atan2(my, mx)

            return mx, my, shoot, dash

        self.input_idle += 1

        if self.input_idle < AUTOPILOT_DELAY:
            self.assist_active = False
            return 0.0, 0.0, shoot, dash

        self.assist_active = True
        target = self.target(fighters)
        if target is None:
            return 0.0, 0.0, False, False

        if self.brain is None:
            self.brain = TransformationAI(self.pid, "tactical")

        action = self.brain.choose(self, target, fighters, self.world)
        self.last_action = "AUTO:" + action
        self.angle = self.brain.intercept_angle(self, target)

        d = distance(self.x, self.y, target.x, target.y)
        dx = target.x - self.x
        dy = target.y - self.y
        nx = dx / max(1.0, d)
        ny = dy / max(1.0, d)
        side = -1 if math.sin(self.world.time * 0.045) < 0 else 1
        sx = -ny * side
        sy = nx * side

        mx = my = 0.0
        auto_shoot = False
        auto_dash = False

        if action == "APPROACH":
            mx, my = nx, ny
        elif action == "RETREAT":
            mx, my = -nx, -ny
        elif action == "STRAFE":
            mx, my = sx + nx * 0.18, sy + ny * 0.18
        elif action == "HOLD":
            if d < 155:
                mx, my = -nx, -ny
            elif d > 330:
                mx, my = nx, ny
        elif action == "DASH":
            auto_dash = self.dash_cd <= 0
            mx, my = ((-nx, -ny) if self.hp < 35 else (sx, sy))
        elif action == "SHOOT":
            mx, my = (nx, ny) if d > 500 else (sx, sy)
            auto_shoot = d < 540

        if self.cooldown <= 0 and d < 540:
            auto_shoot = True

        return (
            mx * AUTOPILOT_STRENGTH,
            my * AUTOPILOT_STRENGTH,
            auto_shoot,
            auto_dash,
        )

    def control(self, fighters, keys):
        if not self.alive:
            return

        if self.ai:
            mx, my, shoot, dash = self.control_ai(fighters)
        else:
            mx, my, shoot, dash = self.control_user(keys, fighters)

        length = math.hypot(mx, my)
        if length > 0:
            mx /= length
            my /= length

        self.vx += mx * MOVE * self.speed
        self.vy += my * MOVE * self.speed

        fx, fy = self.world.memory.influence(self.x, self.y)
        self.vx += fx
        self.vy += fy

        if dash and self.dash_cd <= 0:
            self.vx += math.cos(self.angle) * DASH
            self.vy += math.sin(self.angle) * DASH
            self.dash_cd = 28
            self.dashes += 1
            self.world.memory.remember(self.x, self.y, "DASH", 0.065)
            self.world.graph.observe(self.pid, "DASH")

        self.vx *= 0.90
        self.vy *= 0.90
        self.x += self.vx
        self.y += self.vy

        bounced = False
        if self.x < LEFT + PLAYER_R:
            self.x = LEFT + PLAYER_R
            self.vx = abs(self.vx)
            bounced = True
        elif self.x > RIGHT - PLAYER_R:
            self.x = RIGHT - PLAYER_R
            self.vx = -abs(self.vx)
            bounced = True

        if self.y < BOTTOM + PLAYER_R:
            self.y = BOTTOM + PLAYER_R
            self.vy = abs(self.vy)
            bounced = True
        elif self.y > TOP - PLAYER_R:
            self.y = TOP - PLAYER_R
            self.vy = -abs(self.vy)
            bounced = True

        if bounced:
            self.world.memory.remember(self.x, self.y, "BOUNCE", 0.045)
            self.world.graph.observe(self.pid, "BOUNCE")

        if shoot and self.cooldown <= 0:
            bullets.append(Bullet(
                self.pid,
                self.x + math.cos(self.angle) * 20,
                self.y + math.sin(self.angle) * 20,
                math.cos(self.angle) * BULLET_SPEED,
                math.sin(self.angle) * BULLET_SPEED,
            ))
            self.cooldown = 11
            self.shots += 1
            self.world.graph.observe(self.pid, "SHOOT")

        self.cooldown = max(0, self.cooldown - 1)
        self.dash_cd = max(0, self.dash_cd - 1)

    def damage(self, amount, x, y, attacker_id):
        if not self.alive:
            return

        self.hp = max(0.0, self.hp - amount)
        self.world.memory.remember(x, y, "HIT", 0.085)
        self.world.graph.observe(self.pid, "HIT")
        self.world.graph.observe(attacker_id, "DAMAGE")

        if self.ai:
            self.brain.transitions.observe(self.pid, "HIT")

        if self.hp <= 0:
            self.alive = False
            self.world.memory.remember(self.x, self.y, "BREAK", 0.12)
            self.world.graph.observe(self.pid, "BREAK")


# ------------------------------------------------------------
# DRAWING
# ------------------------------------------------------------
screen = turtle.Screen()
screen.setup(W, H)
screen.bgcolor("#070a12")
screen.title("LAW OF CHANGE : TRANSFORMATION AI")
screen.tracer(False)


draw = turtle.Turtle(visible=False)
draw.penup()
draw.speed(0)

hud = turtle.Turtle(visible=False)
hud.penup()
hud.speed(0)

effect = turtle.Turtle(visible=False)
effect.penup()
effect.speed(0)


def rect(t, x1, y1, x2, y2, color, width=2):
    t.color(color)
    t.pensize(width)
    t.goto(x1, y1)
    t.pendown()
    t.goto(x2, y1)
    t.goto(x2, y2)
    t.goto(x1, y2)
    t.goto(x1, y1)
    t.penup()


def draw_world():
    draw.clear()
    effect.clear()

    danger = world.zone
    border = "#3b536b" if danger < 0.5 else "#7e3444"
    rect(draw, LEFT, BOTTOM, RIGHT, TOP, border, 3)

    # Persistent transformations become visible on the world surface.
    for law in world.memory.laws:
        size = 2 + int(law["strength"] * 10)
        color = {
            "HIT": "#ff667a",
            "BREAK": "#ffbf5a",
            "DASH": "#7b8dff",
            "BOUNCE": "#9df3ff",
            "MISS": "#8894aa",
            "COLLISION": "#b77cff",
        }.get(law["kind"], "#707b90")
        draw.goto(law["x"], law["y"])
        draw.dot(size, color)

    if danger > 0.18:
        draw.goto(0, 0)
        draw.dot(65 + int(110 * danger), "#24131a")

    for b in bullets:
        draw.goto(b.x, b.y)
        draw.dot(7, COLORS[b.owner])

    for f in fighters:
        f.body.goto(f.x, f.y)

        if not f.alive:
            draw.goto(f.x, f.y)
            draw.dot(13, "#301822")
            continue

        draw.goto(f.x, f.y + 27)
        draw.color(f.color)
        draw.write(f.name, align="center", font=("Arial", 9, "bold"))

        draw.color(f.color)
        draw.pensize(4)
        draw.goto(f.x - 22, f.y - 26)
        draw.pendown()
        draw.goto(f.x - 22 + 44 * f.hp / MAX_HP, f.y - 26)
        draw.penup()

        if f.ai:
            draw.color(f.color)
            draw.pensize(1)
            draw.goto(f.x, f.y)
            draw.pendown()
            draw.goto(
                f.x + math.cos(f.angle) * 28,
                f.y + math.sin(f.angle) * 28,
            )
            draw.penup()


def draw_hud():
    hud.clear()
    hud.goto(-545, 330)
    hud.color("#e7edf7")
    hud.write("LAW OF CHANGE : TRANSFORMATION AI", font=("Arial", 16, "bold"))

    hud.goto(-545, 307)
    hud.color("#91a4c2")
    hud.write(
        f"OBSERVE / PREDICT / COMPARE / TRANSFORM / ACT    "
        f"danger={world.zone:.2f}  laws={len(world.memory.laws):03d}  "
        f"transform={world.graph.count():03d}  t={int(world.time):05d}",
        font=("Arial", 9, "normal"),
    )

    y = 278
    for f in fighters:
        state = f.state()
        hud.color(f.color)
        hud.goto(-545, y)

        if f.ai:
            brain = f.brain
            predicted, confidence = brain.predicted_event()
            hud.write(
                f"{f.name:4} HP={int(f.hp):3d} {state:8} "
                f"err={brain.memory.prediction_error:.2f} "
                f"cur={brain.memory.curiosity:.2f} "
                f"changes={len(brain.memory.change_history):3d} "
                f"next={predicted or '-':9} {confidence:.2f}  "
                f"{f.last_action}",
                font=("Consolas", 9, "normal"),
            )
        else:
            mode = "AI-AUTO" if f.input_idle >= AUTOPILOT_DELAY else (
                "AI-ASSIST" if f.input_idle > 0 else "USER"
            )
            hud.write(
                f"YOU  HP={int(f.hp):3d} {state:8} "
                f"ATK={f.attack_power:.2f}  {mode} idle={f.input_idle:02d}",
                font=("Consolas", 9, "normal"),
            )

        y -= 20

    alive = [f for f in fighters if f.alive]
    if len(alive) == 1:
        hud.goto(0, -340)
        hud.color(alive[0].color)
        hud.write(
            f"{alive[0].name} WINS",
            align="center",
            font=("Arial", 24, "bold"),
        )

    hud.goto(-545, -335)
    hud.color("#7e8aa0")
    hud.write(
        "A/D or ←/→ move   W/S or ↑/↓ aim   SPACE shoot   SHIFT dash   "
        "R reset   E forget laws   P pause   |   input = assist / no input = auto",
        font=("Arial", 9, "normal"),
    )


# ------------------------------------------------------------
# INPUT
# ------------------------------------------------------------
keys = set()
paused = False


def key_down(k):
    keys.add(k)


def key_up(k):
    keys.discard(k)


for key in ["Left", "Right", "Up", "Down", "a", "d", "w", "s"]:
    screen.onkeypress(lambda k=key.lower(): key_down(k), key)
    screen.onkeyrelease(lambda k=key.lower(): key_up(k), key)

screen.onkeypress(lambda: key_down("shoot"), "space")
screen.onkeyrelease(lambda: key_up("shoot"), "space")
screen.onkeypress(lambda: key_down("dash"), "Shift_L")
screen.onkeyrelease(lambda: key_up("dash"), "Shift_L")


# ------------------------------------------------------------
# GAME SETUP
# ------------------------------------------------------------
world = World()
fighters = [
    Fighter(0, -380, 0, world, ai=False),
    Fighter(1, 20, 90, world, ai=True, style="aggressive"),
    Fighter(2, 380, -20, world, ai=True, style="tactical"),
]
bullets = []


def reset():
    for f in fighters:
        f.reset()
    bullets.clear()
    global paused
    paused = False


def forget_world():
    world.memory.laws.clear()
    world.graph.edges.clear()
    world.graph.last_event.clear()
    world.graph.event_count.clear()

    for f in fighters:
        if f.ai:
            f.brain.memory.state_history.clear()
            f.brain.memory.change_history.clear()
            f.brain.memory.transition_counts.clear()
            f.brain.memory.context_changes.clear()
            f.brain.memory.prediction_error = 0.0
            f.brain.memory.curiosity = 1.0
            f.brain.recent_events.clear()
            f.brain.last_event = None
            f.brain.last_action = "HOLD"
            f.brain.transitions = TransformationGraph()

    world.memory.save()


def toggle_pause():
    global paused
    paused = not paused


screen.onkey(reset, "r")
screen.onkey(forget_world, "e")
screen.onkey(toggle_pause, "p")
screen.listen()


# ------------------------------------------------------------
# PHYSICS / COMBAT
# ------------------------------------------------------------
def update_bullets():
    survivors = []

    for b in bullets:
        b.x += b.vx
        b.y += b.vy
        b.life -= 1
        hit = False

        for f in fighters:
            if not f.alive or f.pid == b.owner:
                continue

            if distance(b.x, b.y, f.x, f.y) < PLAYER_R + 6:
                attacker = fighters[b.owner]
                amount = 7.0 * attacker.attack_power
                f.damage(amount, b.x, b.y, attacker.pid)
                attacker.hits += 1
                world.graph.observe(attacker.pid, "HIT")
                world.hit_world(b.x, b.y)
                hit = True
                break

        if not hit and b.life > 0 and LEFT < b.x < RIGHT and BOTTOM < b.y < TOP:
            survivors.append(b)
        elif not hit:
            owner = fighters[b.owner]
            world.memory.remember(b.x, b.y, "MISS", 0.025)
            if owner.ai:
                owner.brain.transitions.observe(owner.pid, "MISS")

    bullets[:] = survivors


# ------------------------------------------------------------
# LOOP
# ------------------------------------------------------------
def loop():
    if not paused:
        world.update()
        alive = [f for f in fighters if f.alive]

        if len(alive) > 1:
            for f in fighters:
                f.control(fighters, keys)
            update_bullets()

    draw_world()
    draw_hud()
    screen.update()
    screen.ontimer(loop, FPS_MS)


loop()
turtle.done()
