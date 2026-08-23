# ============================================================
# LAW OF CHANGE : HARD AI BATTLE
#
# YOU + AI-A + AI-B
#
# AI = Observe -> Predict -> Evaluate -> Act -> Remember
#
# Inspired by the uploaded LAW OF CHANGE / TransformationGraph /
# Dynamic World / GHOUL predictive-agent designs.
#
# Controls
#   A/D or Left/Right : move
#   W/S or Up/Down    : aim
#   SPACE             : shoot
#   SHIFT             : dash
#   R                 : reset fighters (AI memory survives)
#   E                 : erase persistent memory
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

MEMORY_FILE = "law_hard_ai_memory.json"

COLORS = ["#00eaff", "#57ff9b", "#ff9f43"]
NAMES = ["YOU", "AI-A", "AI-B"]

ACTIONS = ("APPROACH", "RETREAT", "STRAFE", "HOLD", "DASH", "SHOOT")


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def angle_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


# ------------------------------------------------------------
# PERSISTENT LAW
# ------------------------------------------------------------
class LawMemory:
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
            "x": x,
            "y": y,
            "kind": kind,
            "strength": strength,
            "hits": 1,
        })
        if len(self.laws) > 120:
            self.laws.sort(key=lambda z: z["strength"])
            self.laws.pop(0)

    def influence(self, x, y):
        fx = fy = 0.0
        for law in self.laws:
            d = distance(x, y, law["x"], law["y"])
            if d > 130:
                continue
            w = law["strength"] * (1.0 - d / 130.0)
            if law["kind"] == "HIT":
                fx += math.sin((x - law["x"]) * 0.06) * 0.035 * w
            elif law["kind"] == "BREAK":
                fy += math.copysign(0.05 * w, y - law["y"] or 1)
            elif law["kind"] == "DASH":
                fx += 0.055 * w
            elif law["kind"] == "MISS":
                fy -= 0.025 * w
        return fx, fy

    def decay(self):
        for law in self.laws:
            law["strength"] *= 0.9992
        self.laws = [x for x in self.laws if x["strength"] > 0.025]

    def save(self):
        try:
            with open(MEMORY_FILE, "w", encoding="utf-8") as f:
                json.dump(self.laws, f, ensure_ascii=False)
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
    """Connect recurring changes rather than memorizing labels."""

    def __init__(self):
        self.edges = defaultdict(int)
        self.last = {}

    def observe(self, fighter_id, event):
        previous = self.last.get(fighter_id)
        if previous is not None and previous != event:
            self.edges[tuple(sorted((previous, event)))] += 1
        self.last[fighter_id] = event

    def strength(self, a, b):
        return self.edges.get(tuple(sorted((a, b))), 0)

    def count(self):
        return len(self.edges)


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
# HARD AI MEMORY
# ------------------------------------------------------------
class AIMemory:
    """
    Independent adaptive brain.

    Stores:
      - recent opponent trajectories
      - action outcomes
      - state transition counts
      - prediction error
      - hit / miss positions
      - enemy shooting timing
      - short experience replay
    """

    def __init__(self, pid, style):
        self.pid = pid
        self.style = style
        self.history = defaultdict(lambda: deque(maxlen=48))
        self.action_value = defaultdict(lambda: [0.0] * len(ACTIONS))
        self.action_visits = defaultdict(lambda: [0] * len(ACTIONS))
        self.transitions = defaultdict(int)
        self.experience = deque(maxlen=1600)
        self.enemy_shots = deque(maxlen=120)
        self.enemy_hits = deque(maxlen=120)
        self.enemy_misses = deque(maxlen=120)
        self.prediction_error = 0.0
        self.curiosity = 1.0
        self.last_state = None
        self.last_action = None
        self.last_snapshot = None
        self.learn_steps = 0

    def state(self, me, target, world):
        if target is None:
            return (0, 0, 0, 0, int(me.hp < 50), int(world.zone > 0.5))
        d = distance(me.x, me.y, target.x, target.y)
        relx = int(clamp((target.x - me.x) / 80, -7, 7))
        rely = int(clamp((target.y - me.y) / 70, -5, 5))
        relvx = int(clamp((target.vx - me.vx) / 2.5, -4, 4))
        hp = int(me.hp // 20)
        thp = int(target.hp // 20)
        danger = int(world.zone > 0.5)
        return (relx, rely, relvx, int(d > 300), hp, thp, danger)

    def observe_enemy(self, target, time):
        if target is None:
            return
        seq = self.history[target.pid]
        if seq:
            old = seq[-1]
            predicted_x = old[0] + old[2]
            predicted_y = old[1] + old[3]
            err = distance(predicted_x, predicted_y, target.x, target.y)
            self.prediction_error = 0.97 * self.prediction_error + 0.03 * min(1.0, err / 80.0)
        seq.append((target.x, target.y, target.vx, target.vy, time))
        self.curiosity = clamp(0.65 * self.prediction_error + 0.35 / math.sqrt(1 + len(self.experience)), 0, 1)

    def predict_position(self, target, horizon):
        if target is None:
            return None
        hist = self.history[target.pid]
        if len(hist) < 2:
            return target.x + target.vx * horizon, target.y + target.vy * horizon
        recent = list(hist)[-6:]
        vx = sum(v[2] for v in recent) / len(recent)
        vy = sum(v[3] for v in recent) / len(recent)
        # Slightly damp the prediction so erratic players are not overfit.
        damp = max(0.45, 1.0 - self.prediction_error * 0.55)
        return target.x + vx * horizon * damp, target.y + vy * horizon * damp

    def aim_angle(self, me, target, bullet_speed):
        if target is None:
            return me.angle
        px, py = self.predict_position(target, 8)
        dx = px - me.x
        dy = py - me.y
        return math.atan2(dy, dx)

    def record_result(self, state, action, reward, next_state):
        if state is None or action is None:
            return
        ai = ACTIONS.index(action)
        values = self.action_value[state]
        visits = self.action_visits[state]
        visits[ai] += 1
        alpha = 0.16 if visits[ai] < 15 else 0.07
        future = max(self.action_value[next_state]) if next_state else 0.0
        target = reward + 0.82 * future
        values[ai] += alpha * (target - values[ai])
        self.transitions[(state, action, next_state)] += 1
        self.experience.append((state, action, reward, next_state))
        self.learn_steps += 1

    def replay(self):
        if len(self.experience) < 20:
            return
        sample = random.sample(list(self.experience), min(80, len(self.experience)))
        for state, action, reward, next_state in sample:
            self.record_result(state, action, reward * 0.25, next_state)

    def action_score(self, action, state, me, target, world):
        value = self.action_value[state][ACTIONS.index(action)]
        seen = self.action_visits[state][ACTIONS.index(action)]
        novelty = 0.80 / math.sqrt(seen + 1)

        score = value + novelty * (0.4 + 0.6 * self.curiosity)

        d = distance(me.x, me.y, target.x, target.y) if target else 999
        low = me.hp < 45
        enemy_low = target is not None and target.hp < 35

        if action == "APPROACH":
            score += 0.35 if d > 260 else -0.10
            if enemy_low:
                score += 0.28
        elif action == "RETREAT":
            score += 0.48 if low and d < 240 else -0.08
            score += 0.12 * world.zone
        elif action == "STRAFE":
            score += 0.26 if 120 < d < 360 else 0.05
        elif action == "HOLD":
            score += 0.18 if 170 < d < 320 else -0.10
        elif action == "DASH":
            score += 0.60 if low and d < 260 else 0.12
            score += 0.18 if world.zone > 0.7 else 0.0
        elif action == "SHOOT":
            score += 0.55 if d < 480 else -0.30
            score += 0.20 if target and abs(target.vx) > 2.5 else 0.0

        # Distinct personalities.
        if self.style == "aggressive":
            if action in ("APPROACH", "SHOOT"):
                score += 0.16
        elif self.style == "tactical":
            if action in ("STRAFE", "RETREAT"):
                score += 0.16
        else:
            if action in ("HOLD", "SHOOT", "RETREAT"):
                score += 0.10

        # Avoid repeated action loops.
        if action == self.last_action:
            score -= 0.035
        return score

    def choose(self, me, target, world):
        state = self.state(me, target, world)
        if self.last_state is not None and self.last_action is not None:
            self.record_result(self.last_state, self.last_action, 0.0, state)

        candidates = list(ACTIONS)
        scores = [(self.action_score(a, state, me, target, world), a) for a in candidates]
        scores.sort(reverse=True)

        # Top-choice sampling keeps behavior adaptive instead of robotic.
        top = scores[:3]
        temperature = 0.15 + 0.40 * self.curiosity
        if random.random() < 0.08 + 0.16 * self.curiosity:
            choice = random.choice(top)[1]
        else:
            weights = [math.exp(v / max(0.05, temperature)) for v, _ in top]
            choice = random.choices([a for _, a in top], weights=weights, k=1)[0]

        self.last_state = state
        self.last_action = choice
        return choice


# ------------------------------------------------------------
# ADVANCED OPPONENT MODEL
# ------------------------------------------------------------
class OpponentModel:
    """Track habits instead of only positions."""
    def __init__(self):
        self.data = defaultdict(lambda: {
            "left": 0.0, "right": 0.0, "strafe": 0.0,
            "shoot": 0.0, "dash": 0.0, "turn": 0.0,
            "last_x": None, "last_y": None, "last_vx": 0.0, "last_vy": 0.0,
            "shots": 0, "hits": 0
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
        d["last_x"], d["last_y"] = enemy.x, enemy.y
        d["last_vx"], d["last_vy"] = enemy.vx, enemy.vy

    def tendency(self, enemy_pid, side):
        d = self.data[enemy_pid]
        total = d["left"] + d["right"] + 1.0
        if side < 0:
            return d["left"] / total
        return d["right"] / total

    def dodge_bias(self, enemy_pid):
        d = self.data[enemy_pid]
        total = d["left"] + d["right"] + 1.0
        return (d["right"] - d["left"]) / total


class TacticalPlanner:
    """Scores several short-horizon tactical futures."""
    def __init__(self, brain):
        self.brain = brain

    def danger(self, me, enemies, world):
        value = 0.0
        for e in enemies:
            d = distance(me.x, me.y, e.x, e.y)
            if d < 220:
                value += (220 - d) / 220
            if e.cooldown <= 1 and d < 420:
                value += 0.45
        value += world.zone * 0.7
        return value

    def score(self, action, me, target, enemies, world):
        d = distance(me.x, me.y, target.x, target.y) if target else 999
        danger = self.danger(me, enemies, world)
        low = me.hp < 35
        enemy_low = target is not None and target.hp < 35
        s = 0.0

        if action == "APPROACH":
            s += 0.7 if 220 < d else -0.35
            s += 0.25 if enemy_low else 0
        elif action == "RETREAT":
            s += 1.0 if low else 0.15
            s += 0.2 * danger
        elif action == "STRAFE":
            s += 0.65 if 130 < d < 420 else 0.05
            s += 0.35 * danger
        elif action == "HOLD":
            s += 0.45 if 180 < d < 340 else -0.1
        elif action == "DASH":
            s += 0.9 if danger > 1.1 else 0.25
            s += 0.5 if low else 0
        elif action == "SHOOT":
            s += 0.8 if d < 500 else -0.25
            s += 0.45 if enemy_low else 0
            s += 0.18 * self.brain.curiosity

        # Do not perform actions that are currently proving unreliable.
        key = (me.state(), action, int(d // 80))
        s += self.brain.context_value.get(key, 0.0)
        return s


class AdvancedAIMemory(AIMemory):
    """Prediction + opponent model + tactical planning + adaptive replay."""
    def __init__(self, pid, style):
        super().__init__(pid, style)
        self.opponents = OpponentModel()
        self.context_value = defaultdict(float)
        self.recent_decisions = deque(maxlen=80)
        self.planner = TacticalPlanner(self)
        self.horizon_error = deque(maxlen=120)

    def observe_all(self, me, fighters):
        for enemy in fighters:
            if enemy.pid != me.pid and enemy.alive:
                self.opponents.observe(enemy)
                self.observe_enemy(enemy, self.learn_steps)

    def future_position(self, target, horizon):
        px, py = self.predict_position(target, horizon)
        # Learn systematic lateral bias from the opponent.
        side = self.opponents.dodge_bias(target.pid)
        px += side * min(18.0, horizon * 1.8)
        py += math.sin(self.learn_steps * 0.05 + target.pid) * 4.0
        return px, py

    def intercept_angle(self, me, target):
        best = None
        best_cost = 1e9
        for h in (5, 8, 11, 15):
            px, py = self.future_position(target, h)
            a = math.atan2(py - me.y, px - me.x)
            ex = me.x + math.cos(a) * BULLET_SPEED * h
            ey = me.y + math.sin(a) * BULLET_SPEED * h
            cost = distance(ex, ey, px, py)
            if cost < best_cost:
                best_cost, best = cost, a
            self.horizon_error.append(cost / 120.0)
        return best if best is not None else me.angle

    def choose_advanced(self, me, target, enemies, world):
        state = self.state(me, target, world)
        self.observe_all(me, enemies + [me])

        # Simulate candidate intent for a few horizons.
        scored = []
        for action in ACTIONS:
            s = self.action_score(action, state, me, target, world)
            s += self.planner.score(action, me, target, enemies, world)

            if target is not None and action == "SHOOT":
                # Reward actions whose predicted intercept is stable.
                pred_cost = min(list(self.horizon_error)[-6:], default=1.0)
                s += max(0.0, 0.8 - pred_cost)

            # Anti-pattern: punish repeating the same decision too long.
            if len(self.recent_decisions) >= 4 and all(x == action for x in list(self.recent_decisions)[-4:]):
                s -= 0.35

            scored.append((s, action))

        scored.sort(reverse=True)
        # Personality changes the depth of exploration.
        top_k = 2 if self.style == "aggressive" else 3
        if random.random() < 0.08 + 0.12 * self.curiosity:
            choice = random.choice(scored[:top_k])[1]
        else:
            choice = scored[0][1]

        self.recent_decisions.append(choice)
        self.last_state = state
        self.last_action = choice
        return choice

    def learn_context(self, me, target, reward):
        if target is None or self.last_action is None:
            return
        d = distance(me.x, me.y, target.x, target.y)
        key = (me.state(), self.last_action, int(d // 80))
        self.context_value[key] = 0.94 * self.context_value[key] + 0.06 * reward

    def replay_advanced(self):
        self.replay()
        for item in list(self.experience)[-60:]:
            state, action, reward, next_state = item
            idx = ACTIONS.index(action)
            self.action_value[state][idx] += 0.02 * reward



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
        self.brain = AdvancedAIMemory(pid, style) if ai else None

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
            # Prefer low HP, but not exclusively. Prevents stupid tunneling.
            pressure = enemy.hp * 1.45
            danger = 40 if enemy.hp < 30 else 0
            return d + pressure - danger

        return min(enemies, key=score)

    def control_ai(self, fighters):
        target = self.target(fighters)
        if target is None:
            return

        self.brain.observe_all(self, fighters)
        action = self.brain.choose_advanced(self, target, [f for f in fighters if f.alive and f.pid != self.pid], self.world)
        self.last_action = action

        d = distance(self.x, self.y, target.x, target.y)
        aim = self.brain.intercept_angle(self, target)
        self.angle = aim

        dx = target.x - self.x
        dy = target.y - self.y
        side = -1 if math.sin(self.world.time * 0.045 + self.pid * 2.1) < 0 else 1
        nx = dx / max(1.0, d)
        ny = dy / max(1.0, d)
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
            mx, my = sx + nx * 0.18, sy + ny * 0.18
        elif action == "HOLD":
            if d < 155:
                mx, my = -nx, -ny
            elif d > 330:
                mx, my = nx, ny
        elif action == "DASH":
            dash = self.dash_cd <= 0
            if self.hp < 35:
                mx, my = -nx, -ny
            else:
                mx, my = sx, sy
        elif action == "SHOOT":
            if d > 500:
                mx, my = nx, ny
            elif d < 140 and self.hp > target.hp:
                mx, my = sx - nx * 0.25, sy - ny * 0.25
            else:
                mx, my = sx, sy
            shoot = d < 540

        # Hard safety rule, independent of learned policy.
        if self.hp < 24 and d < 210:
            mx, my = -nx, -ny
            dash = self.dash_cd <= 0

        # Fire when the prediction model has confidence.
        if self.cooldown <= 0 and d < 540:
            prediction = self.brain.prediction_error
            shoot |= prediction < 0.50 or target.hp < 45

        return mx, my, shoot, dash

    def control_user(self, keys):
        mx = int("right" in keys or "d" in keys) - int("left" in keys or "a" in keys)
        my = int("up" in keys or "w" in keys) - int("down" in keys or "s" in keys)
        shoot = "shoot" in keys
        dash = "dash" in keys
        if mx or my:
            self.angle = math.atan2(my, mx)
        return mx, my, shoot, dash

    def control(self, fighters, keys):
        if not self.alive:
            return
        if self.ai:
            mx, my, shoot, dash = self.control_ai(fighters)
        else:
            mx, my, shoot, dash = self.control_user(keys)

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
            self.world.memory.remember(self.x, self.y, "BREAK", 0.035)
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

    def target_from_world(self):
        alive = [f for f in fighters if f.alive and f.pid != self.pid]
        return min(alive, key=lambda f: distance(self.x, self.y, f.x, f.y), default=None)

    def damage(self, amount, x, y, attacker_id):
        if not self.alive:
            return
        self.hp = max(0.0, self.hp - amount)
        self.hits += 0
        self.world.memory.remember(x, y, "HIT", 0.085)
        self.world.graph.observe(self.pid, "HIT")
        self.world.graph.observe(attacker_id, "DAMAGE")
        if self.ai:
            self.brain.enemy_hits.append((self.world.time, x, y, amount))
        if self.hp <= 0:
            self.alive = False
            self.world.memory.remember(self.x, self.y, "BREAK", 0.12)
            self.world.graph.observe(self.pid, "BREAK")


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
        if self.time % 500 == 0:
            for fighter in fighters:
                if fighter.ai:
                    fighter.brain.replay_advanced()

    def hit_world(self, x, y):
        self.zone = min(1.0, self.zone + 0.032)
        self.memory.remember(x, y, "HIT", 0.05)


# ------------------------------------------------------------
# DRAWING
# ------------------------------------------------------------
screen = turtle.Screen()
screen.setup(W, H)
screen.bgcolor("#070a12")
screen.title("LAW OF CHANGE : HARD AI BATTLE")
screen.tracer(False)

draw = turtle.Turtle(visible=False)
draw.penup(); draw.speed(0)
hud = turtle.Turtle(visible=False)
hud.penup(); hud.speed(0)
effect = turtle.Turtle(visible=False)
effect.penup(); effect.speed(0)


def rect(t, x1, y1, x2, y2, color, width=2):
    t.color(color)
    t.pensize(width)
    t.goto(x1, y1)
    t.pendown()
    t.goto(x2, y1); t.goto(x2, y2); t.goto(x1, y2); t.goto(x1, y1)
    t.penup()


def draw_world():
    draw.clear(); effect.clear()
    danger = world.zone
    border = "#3b536b" if danger < 0.5 else "#7e3444"
    rect(draw, LEFT, BOTTOM, RIGHT, TOP, border, 3)

    # remembered laws: the world surface slowly accumulates them
    for law in world.memory.laws:
        size = 2 + int(law["strength"] * 9)
        color = {
            "HIT": "#ff667a",
            "BREAK": "#ffbf5a",
            "DASH": "#7b8dff",
        }.get(law["kind"], "#707b90")
        draw.goto(law["x"], law["y"])
        draw.dot(size, color)

    if danger > 0.18:
        draw.goto(0, 0)
        draw.dot(65 + int(110 * danger), "#24131a")

    # bullets
    for b in bullets:
        draw.goto(b.x, b.y)
        draw.dot(7, COLORS[b.owner])

    # fighters, names, HP
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

        # AI intent line
        if f.ai:
            draw.color(f.color)
            draw.pensize(1)
            draw.goto(f.x, f.y)
            draw.pendown()
            draw.goto(
                f.x + math.cos(f.angle) * 26,
                f.y + math.sin(f.angle) * 26,
            )
            draw.penup()


def draw_hud():
    hud.clear()
    hud.goto(-545, 330)
    hud.color("#e7edf7")
    hud.write("LAW OF CHANGE : HARD AI", font=("Arial", 16, "bold"))

    hud.goto(-545, 307)
    hud.color("#91a4c2")
    hud.write(
        f"OBSERVE / PREDICT / ACT / REMEMBER    "
        f"danger={world.zone:.2f}  laws={len(world.memory.laws):03d}  "
        f"transform={world.graph.count():03d}  t={int(world.time):05d}",
        font=("Arial", 9, "normal"),
    )

    y = 278
    for f in fighters:
        state = f.state()
        if f.ai:
            brain = f.brain
            hud.color(f.color)
            hud.goto(-545, y)
            hud.write(
                f"{f.name:4} HP={int(f.hp):3d} {state:8} "
                f"ATK={f.attack_power:.2f}  "
                f"err={brain.prediction_error:.2f} "
                f"cur={brain.curiosity:.2f}  "
                f"mem={len(brain.experience):4d}  "
                f"{f.last_action}",
                font=("Consolas", 9, "normal"),
            )
        else:
            hud.color(f.color)
            hud.goto(-545, y)
            hud.write(
                f"YOU  HP={int(f.hp):3d} {state:8} ATK={f.attack_power:.2f}",
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
        "R reset   E forget   P pause",
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
    world.graph.last.clear()
    for f in fighters:
        if f.ai:
            f.brain.history.clear()
            f.brain.action_value.clear()
            f.brain.action_visits.clear()
            f.brain.transitions.clear()
            f.brain.experience.clear()
            f.brain.prediction_error = 0.0
            f.brain.curiosity = 1.0
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
                if attacker.ai:
                    attacker.brain.enemy_misses.append((world.time, b.x, b.y))
                hit = True
                break

        if not hit and b.life > 0 and LEFT < b.x < RIGHT and BOTTOM < b.y < TOP:
            survivors.append(b)
        elif not hit:
            owner = fighters[b.owner]
            if owner.ai:
                owner.brain.enemy_misses.append((world.time, b.x, b.y))
                world.memory.remember(b.x, b.y, "MISS", 0.025)

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
