# ============================================================
# LAW OF CHANGE : TRANSFORMATION AI
#
# 2 VS 1
#
# YOU
#   VS
# AI-A + AI-B
#
# NO Q-LEARNING
# NO REWARD
# NO Q-VALUE
# NO EXPERIENCE REPLAY
#
# AI = OBSERVE -> PREDICT -> COMPARE -> LEARN CHANGE -> ACT
#
# AI-A / AI-B are teammates.
# They DO NOT attack each other.
# They cooperate against YOU.
#
# EVOLUTION:
#   SHARED TEAM TRANSFORMATION MEMORY
#   DYNAMIC PRESSURE / FLANK ROLES
#   PREDICTED TARGET FUSION
#   FORMATION CONTROL
#   JOINT TRANSFORMATION GRAPH
#
# FIX:
#   - TeamCoordinationMemory.update() is safe when requester has no AI allies.
#   - YOU never enters AI-team coordination logic, even during autopilot.
#
# ============================================================

import math
import json
import random
import turtle
from collections import defaultdict, deque


# ============================================================
# CONFIG
# ============================================================

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


# ============================================================
# PLAYERS / TEAMS
# ============================================================

COLORS = [
    "#00eaff",   # YOU
    "#57ff9b",   # AI-A
    "#ff9f43",   # AI-B
]

NAMES = [
    "YOU",
    "AI-A",
    "AI-B",
]

TEAMS = [
    0,  # YOU
    1,  # AI-A
    1,  # AI-B
]

TEAM_NAMES = {
    0: "YOU",
    1: "AI-A + AI-B",
}


ACTIONS = (
    "APPROACH",
    "RETREAT",
    "STRAFE",
    "HOLD",
    "DASH",
    "SHOOT",
)


# ------------------------------------------------------------
# USER ASSIST
# ------------------------------------------------------------

ASSIST_STRENGTH = 0.28
AUTOPILOT_DELAY = 12
AUTOPILOT_STRENGTH = 0.78


# ------------------------------------------------------------
# TINY CURIOSITY
# ------------------------------------------------------------

UNKNOWN_BIAS = 0.08

BASE_EXPLORATION = 0.06
CURIOSITY_EXPLORATION = 0.12


# ============================================================
# UTILS
# ============================================================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def angle_diff(a, b):
    d = (a - b + math.pi) % (2 * math.pi) - math.pi
    return abs(d)


def quantize(v, step):
    return int(round(v / step))


def same_team(a, b):
    return a.team == b.team


def enemy_team(a, b):
    return a.team != b.team


# ============================================================
# PERSISTENT LAW
# ============================================================

class LawMemory:

    def __init__(self):
        self.laws = []
        self.load()

    def remember(self, x, y, kind, strength=0.10):

        for law in self.laws:

            if (
                law["kind"] == kind
                and distance(
                    x,
                    y,
                    law["x"],
                    law["y"]
                ) < 85
            ):

                law["x"] = (
                    law["x"] * 0.88
                    + x * 0.12
                )

                law["y"] = (
                    law["y"] * 0.88
                    + y * 0.12
                )

                law["strength"] = min(
                    1.0,
                    law["strength"] + strength
                )

                law["hits"] += 1

                return

        self.laws.append(
            {
                "x": float(x),
                "y": float(y),
                "kind": str(kind),
                "strength": float(strength),
                "hits": 1,
            }
        )

        if len(self.laws) > 160:

            self.laws.sort(
                key=lambda z: z["strength"]
            )

            self.laws.pop(0)

    def influence(self, x, y):

        fx = fy = 0.0

        for law in self.laws:

            d = distance(
                x,
                y,
                law["x"],
                law["y"]
            )

            if d > 140:
                continue

            w = (
                law["strength"]
                * (1.0 - d / 140.0)
            )

            kind = law["kind"]

            if kind == "HIT":

                fx += (
                    math.sin(
                        (x - law["x"]) * 0.06
                    )
                    * 0.05
                    * w
                )

            elif kind == "BOUNCE":

                fy += (
                    math.copysign(
                        0.06 * w,
                        y - law["y"] or 1
                    )
                )

            elif kind == "DASH":

                fx += 0.07 * w

            elif kind == "MISS":

                fy -= 0.035 * w

            elif kind == "COLLISION":

                fx += (
                    law["x"] - x
                ) * 0.0008 * w

                fy += (
                    law["y"] - y
                ) * 0.0008 * w

        return fx, fy

    def decay(self):

        for law in self.laws:
            law["strength"] *= 0.9990

        self.laws = [
            x
            for x in self.laws
            if x["strength"] > 0.02
        ]

    def save(self):

        try:

            with open(
                MEMORY_FILE,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    self.laws,
                    f,
                    ensure_ascii=False,
                    indent=2
                )

        except OSError:
            pass

    def load(self):

        try:

            with open(
                MEMORY_FILE,
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            self.laws = [
                x
                for x in data
                if isinstance(x, dict)
            ]

        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
        ):

            self.laws = []


# ============================================================
# TRANSFORMATION GRAPH
# ============================================================

class TransformationGraph:

    def __init__(self):

        self.edges = defaultdict(int)
        self.last_event = {}
        self.event_count = defaultdict(int)

    def observe(self, fighter_id, event):

        previous = self.last_event.get(
            fighter_id
        )

        self.event_count[event] += 1

        if (
            previous is not None
            and previous != event
        ):

            self.edges[
                (previous, event)
            ] += 1

        self.last_event[
            fighter_id
        ] = event

    def transition_strength(self, a, b):

        return self.edges.get(
            (a, b),
            0
        )

    def predicted_next(
        self,
        event,
        limit=4
    ):

        candidates = []

        for (a, b), count in self.edges.items():

            if a == event:
                candidates.append(
                    (count, b)
                )

        candidates.sort(
            reverse=True
        )

        return candidates[:limit]

    def count(self):

        return len(self.edges)


# ============================================================
# CHANGE MEMORY
# ============================================================

class ChangeMemory:

    def __init__(self):

        self.state_history = deque(
            maxlen=80
        )

        self.change_history = deque(
            maxlen=120
        )

        self.transition_counts = defaultdict(
            int
        )

        self.context_changes = defaultdict(
            lambda: defaultdict(int)
        )

        self.prediction_error = 0.0

        self.curiosity = 1.0

        self.last_prediction = None
        self.last_state = None
        self.last_change = None

        self.learn_steps = 0

    def encode_state(
        self,
        me,
        target,
        world
    ):

        if target is None:

            return (
                quantize(me.x, 80),
                quantize(me.y, 70),
                quantize(me.vx, 2),
                quantize(me.vy, 2),
                int(me.hp // 20),
                int(world.zone > 0.5),
            )

        d = distance(
            me.x,
            me.y,
            target.x,
            target.y
        )

        return (
            clamp(
                quantize(
                    target.x - me.x,
                    80
                ),
                -8,
                8,
            ),

            clamp(
                quantize(
                    target.y - me.y,
                    70
                ),
                -6,
                6,
            ),

            clamp(
                quantize(
                    target.vx - me.vx,
                    2.5
                ),
                -5,
                5,
            ),

            clamp(
                quantize(
                    target.vy - me.vy,
                    2.5
                ),
                -5,
                5,
            ),

            int(me.hp // 20),
            int(target.hp // 20),
            int(d // 150),
            int(world.zone > 0.5),
        )

    def encode_change(
        self,
        me,
        target,
        old_state,
        event
    ):

        if old_state is None:
            return (
                event,
                "INIT"
            )

        speed = math.hypot(
            me.vx,
            me.vy
        )

        dx = (
            me.x
            - (target.x if target else me.x)
        )

        dy = (
            me.y
            - (target.y if target else me.y)
        )

        motion = "STILL"

        if speed > 5.0:
            motion = "FAST"

        elif speed > 1.5:
            motion = "MOVE"

        side = "CENTER"

        if target is not None:

            rel = (
                dx * target.vy
                - dy * target.vx
            )

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

        candidates = (
            self.context_changes
            .get(state)
        )

        if not candidates:
            return None, 0

        best = max(
            candidates.items(),
            key=lambda p: p[1]
        )

        return best[0], best[1]

    def observe(
        self,
        me,
        target,
        world,
        event
    ):

        state = self.encode_state(
            me,
            target,
            world
        )

        change = self.encode_change(
            me,
            target,
            self.last_state,
            event
        )

        predicted, strength = (
            self.predict_change(state)
        )

        if predicted is not None:

            if predicted != change:

                self.prediction_error = (
                    0.96
                    * self.prediction_error
                    + 0.04
                )

            else:

                self.prediction_error = (
                    0.96
                    * self.prediction_error
                )

        if self.last_change is not None:

            self.transition_counts[
                (
                    self.last_change,
                    change
                )
            ] += 1

        self.context_changes[
            state
        ][change] += 1

        self.state_history.append(state)
        self.change_history.append(change)

        self.last_state = state
        self.last_change = change
        self.last_prediction = predicted

        uncertainty = (
            1.0
            / math.sqrt(
                1 + len(self.change_history)
            )
        )

        self.curiosity = clamp(
            0.65 * self.prediction_error
            + 0.35 * uncertainty,
            0.03,
            1.0,
        )

        self.learn_steps += 1

    def predict_from_recent(self, state):

        predicted, count = (
            self.predict_change(state)
        )

        if predicted is None:
            return None, 0.0

        total = sum(
            self.context_changes[state].values()
        )

        confidence = (
            count
            / max(1, total)
        )

        return predicted, confidence

    def transition_score(
        self,
        old_change,
        candidate_change
    ):

        if old_change is None:
            return 0.0

        count = self.transition_counts.get(
            (
                old_change,
                candidate_change
            ),
            0
        )

        return math.log1p(count)


# ============================================================
# ACTION-CONDITIONED DELTA-STATE MEMORY
# ============================================================

class ActionLawMemory:

    def __init__(self):

        self.samples = defaultdict(list)

        self.last_state = None
        self.last_action = None
        self.last_snapshot = None

        self.max_samples_per_key = 32

    @staticmethod
    def make_snapshot(me, target):

        if target is None:

            return {
                "x": me.x,
                "y": me.y,
                "vx": me.vx,
                "vy": me.vy,
                "hp": me.hp,
                "td": 0.0,
            }

        return {
            "x": me.x,
            "y": me.y,
            "vx": me.vx,
            "vy": me.vy,
            "hp": me.hp,
            "td": distance(
                me.x,
                me.y,
                target.x,
                target.y
            ),
        }

    @staticmethod
    def make_delta(before, after):

        return (
            after["x"] - before["x"],
            after["y"] - before["y"],
            after["vx"] - before["vx"],
            after["vy"] - before["vy"],
            after["hp"] - before["hp"],
            0.0,
            after["td"] - before["td"],
        )

    @staticmethod
    def mean_delta(values):

        if not values:
            return None

        n = float(len(values))

        return tuple(
            sum(
                v[i]
                for v in values
            ) / n
            for i in range(
                len(values[0])
            )
        )

    @staticmethod
    def delta_error(a, b):

        if a is None or b is None:
            return 1.0

        weights = (
            1.0,
            1.0,
            0.70,
            0.70,
            0.08,
            0.0,
            0.55,
        )

        err = 0.0

        for i, w in enumerate(weights):

            err += (
                abs(a[i] - b[i])
                * w
            )

        return err

    def observe(
        self,
        state,
        action,
        before,
        after
    ):

        if (
            state is None
            or action is None
            or before is None
            or after is None
        ):
            return

        delta = self.make_delta(
            before,
            after
        )

        key = (
            state,
            action
        )

        bucket = self.samples[key]

        bucket.append(delta)

        if len(bucket) > self.max_samples_per_key:
            del bucket[0]

        self.last_state = state
        self.last_action = action
        self.last_snapshot = after

    def predict(
        self,
        state,
        action
    ):

        bucket = self.samples.get(
            (state, action)
        )

        if not bucket:
            return None, 0.0, 0

        delta = self.mean_delta(bucket)

        confidence = (
            1.0
            - math.exp(
                -len(bucket) / 6.0
            )
        )

        return (
            delta,
            confidence,
            len(bucket)
        )

    def action_confidence(
        self,
        state,
        action
    ):

        _, confidence, count = (
            self.predict(
                state,
                action
            )
        )

        return (
            confidence
            if count
            else 0.0
        )

    def known_actions(self, state):

        result = []

        for action in ACTIONS:

            predicted, confidence, count = (
                self.predict(
                    state,
                    action
                )
            )

            if predicted is not None:

                result.append(
                    (
                        action,
                        predicted,
                        confidence,
                        count,
                    )
                )

        return result

    def best_action_for_delta(
        self,
        state,
        desired_delta
    ):

        best = None

        for action in ACTIONS:

            predicted, confidence, count = (
                self.predict(
                    state,
                    action
                )
            )

            if predicted is None:
                continue

            err = self.delta_error(
                predicted,
                desired_delta
            )

            score = (
                confidence
                / (1.0 + err)
            )

            if (
                best is None
                or score > best[0]
            ):

                best = (
                    score,
                    action,
                    predicted,
                    confidence,
                )

        return best

    def law_count(self):

        return len(
            self.samples
        )

    def clear(self):

        self.samples.clear()

        self.last_state = None
        self.last_action = None
        self.last_snapshot = None


# ============================================================
# TRANSFORMATION CONTROLLER
# ============================================================

class TransformationController:

    def __init__(self):

        self.experiment_bias = 0.50
        self.control_bias = 0.80
        self.novelty_bias = 0.28

    def desired_delta(
        self,
        me,
        target,
        world
    ):

        if target is None:

            return (
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
                0.0,
            )

        dx = target.x - me.x
        dy = target.y - me.y

        d = max(
            1.0,
            math.hypot(dx, dy)
        )

        nx = dx / d
        ny = dy / d

        radial = clamp(
            (d - 260.0)
            / 260.0,
            -1.0,
            1.0,
        )

        tangent = (
            math.sin(
                world.time * 0.045
                + me.pid * 1.37
            )
            * 0.35
        )

        return (
            nx * radial * 4.0
            - ny * tangent * 2.2,

            ny * radial * 4.0
            + nx * tangent * 2.2,

            0.0,
            0.0,
            0.0,
            0.0,

            radial * 18.0,
        )

    def score(
        self,
        state,
        action,
        memory,
        desired_delta,
        curiosity
    ):

        predicted, confidence, count = (
            memory.predict(
                state,
                action
            )
        )

        if predicted is None:

            return (
                self.experiment_bias
                * (
                    0.30
                    + curiosity
                )
                + UNKNOWN_BIAS
            )

        error = memory.delta_error(
            predicted,
            desired_delta
        )

        fit = (
            1.0
            / (1.0 + error)
        )

        controllability = (
            confidence
            * fit
        )

        novelty = (
            (1.0 - confidence)
            * curiosity
        )

        return (
            self.control_bias
            * controllability
            + self.novelty_bias
            * novelty
            + UNKNOWN_BIAS
            * (1.0 - confidence)
        )


# ============================================================
# OPPONENT MODEL
# ============================================================

class OpponentModel:

    def __init__(self):

        self.data = defaultdict(
            lambda: {
                "left": 0.0,
                "right": 0.0,
                "turn": 0.0,
                "last_x": None,
                "last_y": None,
                "last_vx": 0.0,
                "last_vy": 0.0,
            }
        )

    def observe(self, enemy):

        d = self.data[
            enemy.pid
        ]

        if d["last_x"] is not None:

            dx = (
                enemy.x
                - d["last_x"]
            )

            dy = (
                enemy.y
                - d["last_y"]
            )

            if abs(dx) > abs(dy):

                d[
                    "right"
                    if dx > 0
                    else "left"
                ] += 1.0

            if abs(
                dx * d["last_vy"]
                - dy * d["last_vx"]
            ) > 10:

                d["turn"] += 0.5

        d["last_x"] = enemy.x
        d["last_y"] = enemy.y

        d["last_vx"] = enemy.vx
        d["last_vy"] = enemy.vy

    def dodge_bias(self, enemy_pid):

        d = self.data[
            enemy_pid
        ]

        total = (
            d["left"]
            + d["right"]
            + 1.0
        )

        return (
            d["right"]
            - d["left"]
        ) / total


# ============================================================
# SHARED TEAM TRANSFORMATION MEMORY
# ============================================================

class TeamCoordinationMemory:

    def __init__(self):

        self.last_signature = None
        self.transitions = defaultdict(int)

        self.shared_prediction = {
            "x": 0.0,
            "y": 0.0,
            "vx": 0.0,
            "vy": 0.0,
            "confidence": 0.0,
        }

        self.predictions = {}
        self.role_map = {}
        self.last_update = -1
        self.last_target_id = None
        self.coordination_count = 0

        self.recent_joint_changes = deque(
            maxlen=90
        )

    def _signature(
        self,
        target,
        ally_a,
        ally_b
    ):

        if target is None:
            return (
                "NONE",
                "NONE",
                "NONE",
            )

        if ally_a is None or ally_b is None:

            return (
                "SINGLE",
                "ONE",
                int(target.hp // 20),
            )

        d1 = distance(
            ally_a.x,
            ally_a.y,
            target.x,
            target.y
        )

        d2 = distance(
            ally_b.x,
            ally_b.y,
            target.x,
            target.y
        )

        separation = distance(
            ally_a.x,
            ally_a.y,
            ally_b.x,
            ally_b.y
        )

        return (
            "PAIR",
            "A_NEAR" if d1 < d2 else "B_NEAR",
            clamp(
                int(separation // 70),
                0,
                12
            ),
            clamp(
                int(target.hp // 20),
                0,
                5
            ),
        )

    def update_prediction(
        self,
        predictor_id,
        target,
        prediction
    ):

        if target is None:

            self.predictions.pop(
                predictor_id,
                None
            )

            if not self.predictions:
                self.shared_prediction = {
                    "x": 0.0,
                    "y": 0.0,
                    "vx": 0.0,
                    "vy": 0.0,
                    "confidence": 0.0,
                }

            return

        self.predictions[
            predictor_id
        ] = prediction

        valid = [
            p
            for p in self.predictions.values()
            if p is not None
        ]

        if not valid:

            valid = [
                (
                    target.x,
                    target.y,
                    target.vx,
                    target.vy,
                )
            ]

        px = (
            sum(
                p[0]
                for p in valid
            )
            / len(valid)
        )

        py = (
            sum(
                p[1]
                for p in valid
            )
            / len(valid)
        )

        vx = (
            sum(
                p[2]
                for p in valid
            )
            / len(valid)
        )

        vy = (
            sum(
                p[3]
                for p in valid
            )
            / len(valid)
        )

        agreement = 0.0

        if len(valid) >= 2:

            disagreement = distance(
                valid[0][0],
                valid[0][1],
                valid[1][0],
                valid[1][1]
            )

            agreement = clamp(
                1.0
                - disagreement / 260.0,
                0.0,
                1.0
            )

        self.shared_prediction = {
            "x": px,
            "y": py,
            "vx": vx,
            "vy": vy,
            "confidence": clamp(
                0.20
                + 0.25 * min(
                    2,
                    len(valid)
                )
                + 0.25 * agreement,
                0.0,
                1.0,
            ),
        }

    def update(
        self,
        requester,
        fighters
    ):

        # ----------------------------------------------------
        # AI TEAM MEMBERS ONLY
        #
        # YOU has team=0 and ai=False.
        # During user autopilot, requester may be YOU,
        # so allies would otherwise become an empty list.
        #
        # Return a normal nearest-enemy target for YOU instead
        # of running the AI-team "minimum over allies" rule.
        # ----------------------------------------------------

        allies = [
            f
            for f in fighters
            if f.team == requester.team
            and f.ai
            and f.alive
        ]

        enemies = [
            f
            for f in fighters
            if f.team != requester.team
            and f.alive
        ]

        if not enemies:
            self.last_target_id = None
            return None

        if not allies:

            # Safe fallback for YOU / non-AI requesters.
            target = min(
                enemies,
                key=lambda e:
                    distance(
                        requester.x,
                        requester.y,
                        e.x,
                        e.y
                    )
            )

            self.last_target_id = target.pid

            # Do not alter shared AI-team roles or transitions.
            return target

        # ----------------------------------------------------
        # NORMAL AI TEAM TARGETING
        # ----------------------------------------------------

        target = min(
            enemies,
            key=lambda e: min(
                distance(
                    a.x,
                    a.y,
                    e.x,
                    e.y
                )
                for a in allies
            )
        )

        self.last_target_id = target.pid

        # Forget predictions from an old target.
        ai_ids = {
            a.pid
            for a in allies
        }

        stale = [
            pid
            for pid in self.predictions
            if pid not in ai_ids
        ]

        for pid in stale:
            self.predictions.pop(
                pid,
                None
            )

        self.last_update += 1

        if len(allies) >= 2:

            ordered = sorted(
                allies,
                key=lambda a:
                    distance(
                        a.x,
                        a.y,
                        target.x,
                        target.y
                    )
            )

            pressure = ordered[0]
            flanker = ordered[1]

            self.role_map[
                pressure.pid
            ] = "PRESSURE"

            self.role_map[
                flanker.pid
            ] = "FLANK"

            for extra in ordered[2:]:
                self.role_map[
                    extra.pid
                ] = "SUPPORT"

        else:

            self.role_map[
                requester.pid
            ] = "PRESSURE"

        signature = self._signature(
            target,
            allies[0] if allies else None,
            allies[1] if len(allies) > 1 else None,
        )

        if self.last_signature is not None:

            self.transitions[
                (
                    self.last_signature,
                    signature
                )
            ] += 1

        self.last_signature = signature

        self.recent_joint_changes.append(
            (
                self.last_update,
                signature,
            )
        )

        self.coordination_count += 1

        return target

    def role(
        self,
        pid
    ):

        return self.role_map.get(
            pid,
            "PRESSURE"
        )

    def joint_transition_count(self):

        return len(
            self.transitions
        )

    def formation_vector(
        self,
        me,
        target,
        ally,
        role
    ):

        if target is None:

            return 0.0, 0.0

        if ally is None:

            dx = target.x - me.x
            dy = target.y - me.y
            d = max(
                1.0,
                math.hypot(dx, dy)
            )

            return (
                dx / d,
                dy / d
            )

        dx = target.x - me.x
        dy = target.y - me.y

        d = max(
            1.0,
            math.hypot(dx, dy)
        )

        nx = dx / d
        ny = dy / d

        tangent_x = -ny
        tangent_y = nx

        if role == "PRESSURE":

            ax = me.x - ally.x
            ay = me.y - ally.y

            ad = max(
                1.0,
                math.hypot(ax, ay)
            )

            separation_force = clamp(
                (105.0 - ad) / 105.0,
                0.0,
                1.0
            )

            return (
                nx
                + (ax / ad)
                * separation_force
                * 0.85,

                ny
                + (ay / ad)
                * separation_force
                * 0.85,
            )

        side = (
            (
                ally.x - target.x
            ) * tangent_x
            + (
                ally.y - target.y
            ) * tangent_y
        )

        sign = -1.0 if side >= 0 else 1.0

        orbit_x = (
            tangent_x * sign
            - nx * 0.18
        )

        orbit_y = (
            tangent_y * sign
            - ny * 0.18
        )

        desired_distance = 260.0

        radial_error = (
            d
            - desired_distance
        ) / desired_distance

        return (
            orbit_x
            - nx * radial_error * 0.7,

            orbit_y
            - ny * radial_error * 0.7,
        )


# ============================================================
# TRANSFORMATION AI
# ============================================================

class TransformationAI:

    def __init__(
        self,
        pid,
        style
    ):

        self.pid = pid
        self.style = style

        self.memory = ChangeMemory()

        self.action_laws = (
            ActionLawMemory()
        )

        self.controller = (
            TransformationController()
        )

        self.opponents = (
            OpponentModel()
        )

        self.transitions = (
            TransformationGraph()
        )

        self.recent_events = deque(
            maxlen=30
        )

        self.last_action = None
        self.last_event = None

        self.role = "PRESSURE"
        self.team_target_id = None
        self.team_prediction_confidence = 0.0

    def team_target(
        self,
        me,
        fighters,
        world
    ):

        # ----------------------------------------------------
        # YOU is not an AI-team member.
        # Even during autopilot, do not put YOU into
        # AI-A/AI-B coordination.
        # ----------------------------------------------------

        if not me.ai:

            enemies = [
                f
                for f in fighters
                if f.pid != me.pid
                and f.alive
                and f.team != me.team
            ]

            if not enemies:
                self.team_target_id = None
                self.role = "PRESSURE"
                return None

            target = min(
                enemies,
                key=lambda e:
                    distance(
                        me.x,
                        me.y,
                        e.x,
                        e.y
                    )
            )

            self.team_target_id = target.pid
            self.role = "PRESSURE"

            return target

        target = world.team_memory.update(
            me,
            fighters
        )

        self.role = world.team_memory.role(
            me.pid
        )

        if target is not None:
            self.team_target_id = target.pid
        else:
            self.team_target_id = None

        return target

    def observe_all(
        self,
        me,
        fighters,
        world
    ):

        enemies = [
            f
            for f in fighters
            if f.pid != me.pid
            and f.alive
            and f.team != me.team
        ]

        for enemy in enemies:

            self.opponents.observe(
                enemy
            )

        target = self.team_target(
            me,
            fighters,
            world
        )

        if target is None:

            target = min(
                enemies,
                key=lambda e:
                    distance(
                        me.x,
                        me.y,
                        e.x,
                        e.y
                    ),
                default=None,
            )

        current_snapshot = (
            self.action_laws.make_snapshot(
                me,
                target
            )
        )

        if (
            self.action_laws.last_state
            is not None
            and self.action_laws.last_action
            is not None
            and self.action_laws.last_snapshot
            is not None
        ):

            self.action_laws.observe(
                self.action_laws.last_state,
                self.action_laws.last_action,
                self.action_laws.last_snapshot,
                current_snapshot,
            )

        state = self.memory.encode_state(
            me,
            target,
            world
        )

        event = self.current_event(
            me,
            target,
            world
        )

        self.memory.observe(
            me,
            target,
            world,
            event
        )

        self.action_laws.last_state = state
        self.action_laws.last_action = (
            self.last_action
        )

        self.action_laws.last_snapshot = (
            current_snapshot
        )

        self.transitions.observe(
            me.pid,
            event
        )

        self.recent_events.append(
            event
        )

        self.last_event = event

    def current_event(
        self,
        me,
        target,
        world
    ):

        if not me.alive:
            return "BREAK"

        if world.zone > 0.75:
            return "DANGER"

        if target is not None:

            d = distance(
                me.x,
                me.y,
                target.x,
                target.y
            )

            if d < 70:
                return "CLOSE"

            if d < 180:
                return "PRESSURE"

            if d > 480:
                return "DISTANT"

        speed = math.hypot(
            me.vx,
            me.vy
        )

        if speed < 0.4:
            return "STILL"

        if speed > 6.5:
            return "FAST"

        return "MOVE"

    def shared_target_prediction(
        self,
        me,
        target,
        world,
        fighters
    ):

        if target is None:
            return None

        local_pred = self.predict_position(
            target,
            10
        )

        if local_pred is not None:

            lx, ly = local_pred

            local_tuple = (
                lx,
                ly,
                target.vx,
                target.vy,
            )

        else:

            local_tuple = None

        world.team_memory.update_prediction(
            self.pid,
            target,
            local_tuple
        )

        prediction = (
            world.team_memory.shared_prediction
        )

        self.team_prediction_confidence = (
            prediction["confidence"]
        )

        return (
            prediction["x"],
            prediction["y"],
            prediction["vx"],
            prediction["vy"],
        )

    def teammate(
        self,
        me,
        fighters
    ):

        allies = [
            f
            for f in fighters
            if f.pid != me.pid
            and f.alive
            and f.team == me.team
            and f.ai
        ]

        if not allies:
            return None

        return min(
            allies,
            key=lambda a:
                distance(
                    me.x,
                    me.y,
                    a.x,
                    a.y
                )
        )

    def predicted_event(self):

        if not self.recent_events:
            return None, 0.0

        event = self.recent_events[-1]

        candidates = (
            self.transitions.predicted_next(
                event,
                limit=3
            )
        )

        if not candidates:
            return None, 0.0

        count, next_event = (
            candidates[0]
        )

        total = sum(
            c
            for (a, _), c
            in self.transitions.edges.items()
            if a == event
        )

        confidence = (
            count
            / max(1, total)
        )

        return (
            next_event,
            confidence
        )

    def score_action(
        self,
        action,
        me,
        target,
        enemies,
        world
    ):

        state = (
            self.memory.last_state
        )

        desired = (
            self.controller.desired_delta(
                me,
                target,
                world
            )
        )

        return self.controller.score(
            state,
            action,
            self.action_laws,
            desired,
            self.memory.curiosity
        )

    def choose(
        self,
        me,
        target,
        fighters,
        world
    ):

        enemies = [
            f
            for f in fighters
            if f.pid != me.pid
            and f.alive
            and f.team != me.team
        ]

        self.observe_all(
            me,
            fighters,
            world
        )

        scored = [
            (
                self.score_action(
                    action,
                    me,
                    target,
                    enemies,
                    world
                ),
                action
            )
            for action in ACTIONS
        ]

        scored.sort(
            reverse=True
        )

        uncertainty = (
            self.memory.curiosity
        )

        exploration_probability = (
            BASE_EXPLORATION
            + CURIOSITY_EXPLORATION
            * uncertainty
        )

        if random.random() < (
            exploration_probability
        ):

            top_k = (
                3
                if uncertainty > 0.45
                else 2
            )

            action = random.choice(
                scored[:top_k]
            )[1]

        else:

            action = scored[0][1]

        self.last_action = action

        return action

    def predict_position(
        self,
        target,
        horizon
    ):

        if target is None:
            return None

        hist = self.opponents.data[
            target.pid
        ]

        vx = hist["last_vx"]
        vy = hist["last_vy"]

        bias = (
            self.opponents.dodge_bias(
                target.pid
            )
        )

        damp = max(
            0.45,
            1.0
            - self.memory.prediction_error
            * 0.5
        )

        return (
            target.x
            + vx * horizon * damp
            + bias * 2.0 * horizon,

            target.y
            + vy * horizon * damp,
        )

    def intercept_angle(
        self,
        me,
        target
    ):

        if target is None:
            return me.angle

        best_angle = me.angle
        best_error = 1e9

        for h in (
            5,
            8,
            11,
            15
        ):

            pred = (
                self.predict_position(
                    target,
                    h
                )
            )

            if pred is None:
                continue

            px, py = pred

            a = math.atan2(
                py - me.y,
                px - me.x
            )

            ex = (
                me.x
                + math.cos(a)
                * BULLET_SPEED
                * h
            )

            ey = (
                me.y
                + math.sin(a)
                * BULLET_SPEED
                * h
            )

            err = distance(
                ex,
                ey,
                px,
                py
            )

            if err < best_error:

                best_error = err
                best_angle = a

        return best_angle


# ============================================================
# BULLET
# ============================================================

class Bullet:

    def __init__(
        self,
        owner,
        x,
        y,
        vx,
        vy
    ):

        self.owner = owner

        self.x = x
        self.y = y

        self.vx = vx
        self.vy = vy

        self.life = BULLET_LIFE


# ============================================================
# WORLD
# ============================================================

class World:

    def __init__(self):

        self.time = 0
        self.zone = 0.0

        self.memory = LawMemory()

        self.graph = (
            TransformationGraph()
        )

        self.team_memory = (
            TeamCoordinationMemory()
        )

    def update(self):

        self.time += 1
        self.zone *= 0.995

        if self.time % 180 == 0:
            self.memory.decay()

        if self.time % 600 == 0:
            self.memory.save()

    def hit_world(
        self,
        x,
        y
    ):

        self.zone = min(
            1.0,
            self.zone + 0.032
        )

        self.memory.remember(
            x,
            y,
            "HIT",
            0.05
        )


# ============================================================
# FIGHTER
# ============================================================

class Fighter:

    def __init__(
        self,
        pid,
        x,
        y,
        world,
        ai=False,
        style="tactical"
    ):

        self.pid = pid

        self.name = NAMES[pid]
        self.color = COLORS[pid]

        self.team = TEAMS[pid]

        self.world = world

        self.ai = ai
        self.style = style

        self.spawn_x = x
        self.spawn_y = y

        self.brain = (
            TransformationAI(
                pid,
                style
            )
            if ai
            else None
        )

        self.body = turtle.Turtle(
            shape="circle"
        )

        self.body.penup()
        self.body.speed(0)

        self.body.color(
            self.color
        )

        self.body.shapesize(
            1.2,
            1.2
        )

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

        if self.brain is not None:
            self.brain.role = (
                "PRESSURE"
                if self.pid == 1
                else "FLANK"
            )

        self.body.goto(
            self.x,
            self.y
        )

    @property
    def attack_power(self):

        return (
            1.0
            + (
                1.0
                - self.hp / MAX_HP
            ) * 1.55
        )

    @property
    def speed(self):

        return (
            1.0
            + 0.20
            * (
                1.0
                - self.hp / MAX_HP
            )
        )

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

    def target(
        self,
        fighters
    ):

        enemies = [
            f
            for f in fighters
            if f.pid != self.pid
            and f.alive
            and f.team != self.team
        ]

        if not enemies:
            return None

        shared_id = getattr(
            self.world.team_memory,
            "last_target_id",
            None
        )

        if shared_id is not None:

            shared = next(
                (
                    e
                    for e in enemies
                    if e.pid == shared_id
                ),
                None
            )

            if shared is not None:
                return shared

        def score(enemy):

            d = distance(
                self.x,
                self.y,
                enemy.x,
                enemy.y
            )

            pressure = (
                enemy.hp * 1.45
            )

            danger = (
                40
                if enemy.hp < 30
                else 0
            )

            return (
                d
                + pressure
                - danger
            )

        return min(
            enemies,
            key=score
        )

    def control_ai(
        self,
        fighters
    ):

        target = self.target(
            fighters
        )

        if target is None:

            return (
                0.0,
                0.0,
                False,
                False
            )

        action = (
            self.brain.choose(
                self,
                target,
                fighters,
                self.world
            )
        )

        self.last_action = action

        role = self.brain.role

        ally = self.brain.teammate(
            self,
            fighters
        )

        team_fx, team_fy = (
            self.world.team_memory
            .formation_vector(
                self,
                target,
                ally,
                role,
            )
        )

        shared_prediction = (
            self.brain.shared_target_prediction(
                self,
                target,
                self.world,
                fighters
            )
        )

        if shared_prediction is not None:

            px, py, pvx, pvy = (
                shared_prediction
            )

            self.angle = math.atan2(
                py + pvy * 4.0 - self.y,
                px + pvx * 4.0 - self.x
            )

        else:

            self.angle = (
                self.brain.intercept_angle(
                    self,
                    target
                )
            )

        state = (
            self.brain.memory.last_state
        )

        predicted, confidence, count = (
            self.brain.action_laws.predict(
                state,
                action
            )
        )

        mx = my = 0.0

        shoot = False
        dash = False

        if predicted is not None:

            (
                dx,
                dy,
                dvx,
                dvy,
                _dhp,
                _dhtarget,
                _dd
            ) = predicted

            mx += (
                dx
                / max(
                    1.0,
                    MOVE
                )
            )

            my += (
                dy
                / max(
                    1.0,
                    MOVE
                )
            )

            mx += (
                dvx * 0.35
            )

            my += (
                dvy * 0.35
            )

        else:

            desired = (
                self.brain.controller
                .desired_delta(
                    self,
                    target,
                    self.world
                )
            )

            mx = (
                desired[0]
                / max(
                    1.0,
                    MOVE
                )
            )

            my = (
                desired[1]
                / max(
                    1.0,
                    MOVE
                )
            )

        formation_gain = (
            0.42
            if role == "PRESSURE"
            else 0.68
        )

        mx += (
            team_fx
            * formation_gain
        )

        my += (
            team_fy
            * formation_gain
        )

        if action == "SHOOT":

            d_target = distance(
                self.x,
                self.y,
                target.x,
                target.y
            )

            shoot = (
                self.cooldown <= 0
                and (
                    (
                        role == "FLANK"
                        and d_target < 520
                    )
                    or
                    (
                        role == "PRESSURE"
                        and d_target < 600
                    )
                )
            )

        elif action == "DASH":

            dash = (
                self.dash_cd <= 0
            )

        length = math.hypot(
            mx,
            my
        )

        if length > 1.0:

            mx /= length
            my /= length

        _ = (
            confidence,
            count
        )

        return (
            mx,
            my,
            shoot,
            dash
        )

    def control_user(
        self,
        keys,
        fighters
    ):

        ux = (
            int(
                "right" in keys
                or "d" in keys
            )
            -
            int(
                "left" in keys
                or "a" in keys
            )
        )

        uy = (
            int(
                "up" in keys
                or "w" in keys
            )
            -
            int(
                "down" in keys
                or "s" in keys
            )
        )

        shoot = (
            "shoot" in keys
        )

        dash = (
            "dash" in keys
        )

        has_move_input = bool(
            ux or uy
        )

        if has_move_input:

            self.input_idle = 0
            self.assist_active = True

            length = math.hypot(
                ux,
                uy
            )

            ux /= length
            uy /= length

            enemies = [
                f
                for f in fighters
                if f.pid != self.pid
                and f.alive
                and f.team != self.team
            ]

            target = min(
                enemies,
                key=lambda f:
                    distance(
                        self.x,
                        self.y,
                        f.x,
                        f.y
                    ),
                default=None,
            )

            ax = ay = 0.0

            if target is not None:

                d = distance(
                    self.x,
                    self.y,
                    target.x,
                    target.y
                )

                dx = (
                    target.x
                    - self.x
                )

                dy = (
                    target.y
                    - self.y
                )

                nx = (
                    dx
                    / max(
                        1.0,
                        d
                    )
                )

                ny = (
                    dy
                    / max(
                        1.0,
                        d
                    )
                )

                if d < 170:

                    ax = -nx
                    ay = -ny

                elif d > 430:

                    ax = nx
                    ay = ny

                else:

                    ax = -ny
                    ay = nx

                fx, fy = (
                    self.world.memory
                    .influence(
                        self.x,
                        self.y
                    )
                )

                ax += fx * 2.0
                ay += fy * 2.0

                alen = math.hypot(
                    ax,
                    ay
                )

                if alen > 0:

                    ax /= alen
                    ay /= alen

            mx = (
                ux
                * (
                    1.0
                    - ASSIST_STRENGTH
                )
                + ax
                * ASSIST_STRENGTH
            )

            my = (
                uy
                * (
                    1.0
                    - ASSIST_STRENGTH
                )
                + ay
                * ASSIST_STRENGTH
            )

            if mx or my:

                self.angle = math.atan2(
                    my,
                    mx
                )

            return (
                mx,
                my,
                shoot,
                dash
            )

        self.input_idle += 1

        if (
            self.input_idle
            < AUTOPILOT_DELAY
        ):

            self.assist_active = False

            return (
                0.0,
                0.0,
                shoot,
                dash
            )

        self.assist_active = True

        target = self.target(
            fighters
        )

        if target is None:

            return (
                0.0,
                0.0,
                False,
                False
            )

        if self.brain is None:

            self.brain = (
                TransformationAI(
                    self.pid,
                    "tactical"
                )
            )

        mx, my, shoot, dash = (
            self.control_ai(
                fighters
            )
        )

        self.last_action = (
            "AUTO:"
            + self.last_action
        )

        self.assist_active = True

        return (
            mx * AUTOPILOT_STRENGTH,
            my * AUTOPILOT_STRENGTH,
            shoot,
            dash
        )

    def control(
        self,
        fighters,
        keys
    ):

        if not self.alive:
            return

        if self.ai:

            mx, my, shoot, dash = (
                self.control_ai(
                    fighters
                )
            )

        else:

            mx, my, shoot, dash = (
                self.control_user(
                    keys,
                    fighters
                )
            )

        length = math.hypot(
            mx,
            my
        )

        if length > 0:

            mx /= length
            my /= length

        self.vx += (
            mx
            * MOVE
            * self.speed
        )

        self.vy += (
            my
            * MOVE
            * self.speed
        )

        fx, fy = (
            self.world.memory
            .influence(
                self.x,
                self.y
            )
        )

        self.vx += fx
        self.vy += fy

        if (
            dash
            and self.dash_cd <= 0
        ):

            self.vx += (
                math.cos(self.angle)
                * DASH
            )

            self.vy += (
                math.sin(self.angle)
                * DASH
            )

            self.dash_cd = 28

            self.dashes += 1

            self.world.memory.remember(
                self.x,
                self.y,
                "DASH",
                0.065
            )

            self.world.graph.observe(
                self.pid,
                "DASH"
            )

        self.vx *= 0.90
        self.vy *= 0.90

        self.x += self.vx
        self.y += self.vy

        bounced = False

        if self.x < LEFT + PLAYER_R:

            self.x = (
                LEFT
                + PLAYER_R
            )

            self.vx = abs(
                self.vx
            )

            bounced = True

        elif self.x > RIGHT - PLAYER_R:

            self.x = (
                RIGHT
                - PLAYER_R
            )

            self.vx = -abs(
                self.vx
            )

            bounced = True

        if self.y < BOTTOM + PLAYER_R:

            self.y = (
                BOTTOM
                + PLAYER_R
            )

            self.vy = abs(
                self.vy
            )

            bounced = True

        elif self.y > TOP - PLAYER_R:

            self.y = (
                TOP
                - PLAYER_R
            )

            self.vy = -abs(
                self.vy
            )

            bounced = True

        if bounced:

            self.world.memory.remember(
                self.x,
                self.y,
                "BOUNCE",
                0.045
            )

            self.world.graph.observe(
                self.pid,
                "BOUNCE"
            )

        if (
            shoot
            and self.cooldown <= 0
        ):

            bullets.append(
                Bullet(
                    self.pid,
                    self.x
                    + math.cos(
                        self.angle
                    ) * 20,
                    self.y
                    + math.sin(
                        self.angle
                    ) * 20,
                    math.cos(
                        self.angle
                    )
                    * BULLET_SPEED,
                    math.sin(
                        self.angle
                    )
                    * BULLET_SPEED,
                )
            )

            self.cooldown = 11

            self.shots += 1

            self.world.graph.observe(
                self.pid,
                "SHOOT"
            )

        self.cooldown = max(
            0,
            self.cooldown - 1
        )

        self.dash_cd = max(
            0,
            self.dash_cd - 1
        )

    def damage(
        self,
        amount,
        x,
        y,
        attacker_id
    ):

        if not self.alive:
            return

        attacker = fighters[attacker_id]

        if attacker.team == self.team:
            return

        self.hp = max(
            0.0,
            self.hp - amount
        )

        self.world.memory.remember(
            x,
            y,
            "HIT",
            0.085
        )

        self.world.graph.observe(
            self.pid,
            "HIT"
        )

        self.world.graph.observe(
            attacker_id,
            "DAMAGE"
        )

        if self.ai:

            self.brain.transitions.observe(
                self.pid,
                "HIT"
            )

        if self.hp <= 0:

            self.alive = False

            self.world.memory.remember(
                self.x,
                self.y,
                "BREAK",
                0.12
            )

            self.world.graph.observe(
                self.pid,
                "BREAK"
            )


# ============================================================
# DRAWING
# ============================================================

screen = turtle.Screen()

screen.setup(
    W,
    H
)

screen.bgcolor(
    "#070a12"
)

screen.title(
    "LAW OF CHANGE : 2 VS 1 TINY CURIOSITY / FIXED"
)

screen.tracer(False)


draw = turtle.Turtle(
    visible=False
)

draw.penup()
draw.speed(0)


hud = turtle.Turtle(
    visible=False
)

hud.penup()
hud.speed(0)


effect = turtle.Turtle(
    visible=False
)

effect.penup()
effect.speed(0)


def rect(
    t,
    x1,
    y1,
    x2,
    y2,
    color,
    width=2
):

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

    border = (
        "#3b536b"
        if danger < 0.5
        else "#7e3444"
    )

    rect(
        draw,
        LEFT,
        BOTTOM,
        RIGHT,
        TOP,
        border,
        3
    )

    for law in world.memory.laws:

        size = (
            2
            + int(
                law["strength"] * 10
            )
        )

        color = {
            "HIT": "#ff667a",
            "BREAK": "#ffbf5a",
            "DASH": "#7b8dff",
            "BOUNCE": "#9df3ff",
            "MISS": "#8894aa",
            "COLLISION": "#b77cff",
        }.get(
            law["kind"],
            "#707b90"
        )

        draw.goto(
            law["x"],
            law["y"]
        )

        draw.dot(
            size,
            color
        )

    if danger > 0.18:

        draw.goto(
            0,
            0
        )

        draw.dot(
            65
            + int(
                110 * danger
            ),
            "#24131a"
        )

    for b in bullets:

        draw.goto(
            b.x,
            b.y
        )

        draw.dot(
            7,
            COLORS[b.owner]
        )

    for f in fighters:

        f.body.goto(
            f.x,
            f.y
        )

        if not f.alive:

            draw.goto(
                f.x,
                f.y
            )

            draw.dot(
                13,
                "#301822"
            )

            continue

        draw.goto(
            f.x,
            f.y + 27
        )

        draw.color(
            f.color
        )

        draw.write(
            f.name,
            align="center",
            font=(
                "Arial",
                9,
                "bold"
            )
        )

        draw.color(
            f.color
        )

        draw.pensize(4)

        draw.goto(
            f.x - 22,
            f.y - 26
        )

        draw.pendown()

        draw.goto(
            f.x
            - 22
            + 44
            * f.hp
            / MAX_HP,
            f.y - 26
        )

        draw.penup()

        if f.ai:

            draw.color(
                f.color
            )

            draw.pensize(1)

            draw.goto(
                f.x,
                f.y
            )

            draw.pendown()

            draw.goto(
                f.x
                + math.cos(
                    f.angle
                ) * 28,

                f.y
                + math.sin(
                    f.angle
                ) * 28,
            )

            draw.penup()


def draw_hud():

    hud.clear()

    hud.goto(
        -545,
        330
    )

    hud.color(
        "#e7edf7"
    )

    hud.write(
        "LAW OF CHANGE : 2 VS 1 / SHARED TRANSFORMATION",
        font=(
            "Arial",
            16,
            "bold"
        )
    )

    hud.goto(
        -545,
        307
    )

    hud.color(
        "#91a4c2"
    )

    hud.write(
        f"YOU  VS  AI-A + AI-B    "
        f"OBSERVE / PREDICT / COMPARE / "
        f"LEARN CHANGE / ACT    "
        f"danger={world.zone:.2f}  "
        f"laws={len(world.memory.laws):03d}  "
        f"transform={world.graph.count():03d}  "
        f"t={int(world.time):05d}",
        font=(
            "Arial",
            9,
            "normal"
        )
    )

    hud.goto(
        -545,
        292
    )

    hud.color(
        "#7689a8"
    )

    hud.write(
        f"shared-target={getattr(world.team_memory, 'last_target_id', '-') }  "
        f"joint-laws={world.team_memory.joint_transition_count():03d}  "
        f"coordination={world.team_memory.coordination_count:04d}",
        font=(
            "Consolas",
            8,
            "normal"
        )
    )

    y = 268

    for f in fighters:

        state = f.state()

        hud.color(
            f.color
        )

        hud.goto(
            -545,
            y
        )

        if f.ai:

            brain = f.brain

            predicted, confidence = (
                brain.predicted_event()
            )

            hud.write(
                f"{f.name:4} "
                f"TEAM=AI "
                f"{brain.role:8} "
                f"HP={int(f.hp):3d} "
                f"{state:8} "
                f"err={brain.memory.prediction_error:.2f} "
                f"cur={brain.memory.curiosity:.2f} "
                f"changes={len(brain.memory.change_history):3d} "
                f"laws={brain.action_laws.law_count():3d} "
                f"team={world.team_memory.joint_transition_count():3d} "
                f"next={predicted or '-':9} "
                f"{confidence:.2f}  "
                f"{f.last_action or '-'}",
                font=(
                    "Consolas",
                    9,
                    "normal"
                )
            )

        else:

            mode = (
                "AI-AUTO"
                if f.input_idle
                >= AUTOPILOT_DELAY
                else
                (
                    "AI-ASSIST"
                    if f.input_idle > 0
                    else "USER"
                )
            )

            hud.write(
                f"YOU  TEAM=YOU "
                f"HP={int(f.hp):3d} "
                f"{state:8} "
                f"ATK={f.attack_power:.2f}  "
                f"{mode} "
                f"idle={f.input_idle:02d}",
                font=(
                    "Consolas",
                    9,
                    "normal"
                )
            )

        y -= 20

    alive_user = any(
        f.alive and f.team == 0
        for f in fighters
    )

    alive_ai = any(
        f.alive and f.team == 1
        for f in fighters
    )

    if alive_user and not alive_ai:

        hud.goto(
            0,
            -340
        )

        hud.color(
            COLORS[0]
        )

        hud.write(
            "YOU WINS",
            align="center",
            font=(
                "Arial",
                24,
                "bold"
            )
        )

    elif alive_ai and not alive_user:

        hud.goto(
            0,
            -340
        )

        hud.color(
            COLORS[1]
        )

        hud.write(
            "AI-A + AI-B WIN",
            align="center",
            font=(
                "Arial",
                24,
                "bold"
            )
        )

    hud.goto(
        -545,
        -335
    )

    hud.color(
        "#7e8aa0"
    )

    hud.write(
        "A/D or ←/→ move   "
        "W/S or ↑/↓ aim   "
        "SPACE shoot   "
        "SHIFT dash   "
        "R reset   "
        "E forget laws   "
        "P pause   "
        "|   "
        "YOU vs AI-A + AI-B",
        font=(
            "Arial",
            9,
            "normal"
        )
    )


# ============================================================
# INPUT
# ============================================================

keys = set()
paused = False


def key_down(k):
    keys.add(k)


def key_up(k):
    keys.discard(k)


for key in [
    "Left",
    "Right",
    "Up",
    "Down",
    "a",
    "d",
    "w",
    "s",
]:

    screen.onkeypress(
        lambda k=key.lower():
            key_down(k),
        key
    )

    screen.onkeyrelease(
        lambda k=key.lower():
            key_up(k),
        key
    )


screen.onkeypress(
    lambda:
        key_down("shoot"),
    "space"
)

screen.onkeyrelease(
    lambda:
        key_up("shoot"),
    "space"
)

screen.onkeypress(
    lambda:
        key_down("dash"),
    "Shift_L"
)

screen.onkeyrelease(
    lambda:
        key_up("dash"),
    "Shift_L"
)


# ============================================================
# GAME SETUP
# ============================================================

world = World()

fighters = [

    Fighter(
        0,
        -380,
        0,
        world,
        ai=False
    ),

    Fighter(
        1,
        20,
        90,
        world,
        ai=True,
        style="aggressive"
    ),

    Fighter(
        2,
        380,
        -20,
        world,
        ai=True,
        style="tactical"
    ),

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

    world.team_memory.last_signature = None
    world.team_memory.last_target_id = None
    world.team_memory.transitions.clear()
    world.team_memory.predictions.clear()
    world.team_memory.role_map.clear()
    world.team_memory.recent_joint_changes.clear()
    world.team_memory.coordination_count = 0
    world.team_memory.last_update = -1

    world.team_memory.shared_prediction = {
        "x": 0.0,
        "y": 0.0,
        "vx": 0.0,
        "vy": 0.0,
        "confidence": 0.0,
    }

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
            f.brain.last_action = None
            f.brain.team_target_id = None
            f.brain.team_prediction_confidence = 0.0

            f.brain.action_laws.clear()

            f.brain.transitions = (
                TransformationGraph()
            )

    world.memory.save()


def toggle_pause():

    global paused

    paused = not paused


screen.onkey(
    reset,
    "r"
)

screen.onkey(
    forget_world,
    "e"
)

screen.onkey(
    toggle_pause,
    "p"
)

screen.listen()


# ============================================================
# PHYSICS / COMBAT
# ============================================================

def update_bullets():

    survivors = []

    for b in bullets:

        b.x += b.vx
        b.y += b.vy

        b.life -= 1

        hit = False

        attacker = fighters[
            b.owner
        ]

        for f in fighters:

            if (
                not f.alive
                or f.pid == b.owner
            ):
                continue

            if f.team == attacker.team:
                continue

            if (
                distance(
                    b.x,
                    b.y,
                    f.x,
                    f.y
                )
                < PLAYER_R + 6
            ):

                amount = (
                    7.0
                    * attacker.attack_power
                )

                f.damage(
                    amount,
                    b.x,
                    b.y,
                    attacker.pid
                )

                attacker.hits += 1

                world.graph.observe(
                    attacker.pid,
                    "HIT"
                )

                world.hit_world(
                    b.x,
                    b.y
                )

                hit = True

                break

        if (
            not hit
            and b.life > 0
            and LEFT < b.x < RIGHT
            and BOTTOM < b.y < TOP
        ):

            survivors.append(b)

        elif not hit:

            owner = fighters[
                b.owner
            ]

            world.memory.remember(
                b.x,
                b.y,
                "MISS",
                0.025
            )

            if owner.ai:

                owner.brain.transitions.observe(
                    owner.pid,
                    "MISS"
                )

    bullets[:] = survivors


# ============================================================
# LOOP
# ============================================================

def loop():

    if not paused:

        world.update()

        alive_user = any(
            f.alive and f.team == 0
            for f in fighters
        )

        alive_ai = any(
            f.alive and f.team == 1
            for f in fighters
        )

        if alive_user and alive_ai:

            for f in fighters:

                f.control(
                    fighters,
                    keys
                )

            update_bullets()

    draw_world()

    draw_hud()

    screen.update()

    screen.ontimer(
        loop,
        FPS_MS
    )


# ============================================================
# START
# ============================================================

loop()

turtle.done()
