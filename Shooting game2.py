# ============================================================
# LAW OF CHANGE : EVOLVING WORLD v5
#
# THE WORLD DOES NOT DIRECTLY CONTROL THE AI.
#
# Instead:
#
#   EVENT
#      ↓
#   TRANSFORMATION
#      ↓
#   LAW
#      ↓
#   META-LAW
#      ↓
#   WORLD MODEL
#      ↓
#   AI PREDICTION
#      ↓
#   ACTION
#      ↓
#   NEW EVENT
#
# Important change from v4:
#
#   LAW is NOT permanent acceleration.
#
#   LAW influences:
#       - danger
#       - curvature
#       - preference
#       - prediction
#
#   This prevents the whole world from collapsing
#   into a corner or diagonal attractor.
#
# Controls
#   A/D or Left/Right : move
#   W/S or Up/Down    : aim
#   SPACE             : shoot
#   SHIFT             : dash
#   R                 : reset fighters
#   E                 : erase world memory
#   P                 : pause
# ============================================================

import math
import json
import random
import turtle
from collections import defaultdict, deque


# ============================================================
# CONFIG
# ============================================================

SCREEN_W = 1200
SCREEN_H = 780

LEFT = -560
RIGHT = 560
BOTTOM = -300
TOP = 250

FPS_MS = 28

PLAYER_R = 16

MOVE_ACCEL = 1.0
MAX_SPEED = 7.5

FRICTION = 0.86

DASH_POWER = 7.0
DASH_COOLDOWN = 28

BULLET_SPEED = 13.0
BULLET_LIFE = 85
BULLET_RADIUS = 5

MAX_HP = 100.0

MEMORY_FILE = "law_evolving_world_v5.json"

LAW_THRESHOLD = 4
LAW_RADIUS = 100

MAX_LAWS = 220
MAX_META_LAWS = 160

WORLD_STEER_LIMIT = 0.65

COLORS = [
    "#00eaff",
    "#57ff9b",
    "#ff9f43",
]

NAMES = [
    "YOU",
    "AI-A",
    "AI-B",
]

ACTIONS = (
    "APPROACH",
    "RETREAT",
    "STRAFE",
    "HOLD",
    "DASH",
    "SHOOT",
)


# ============================================================
# HELPERS
# ============================================================

def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def distance(ax, ay, bx, by):
    return math.hypot(ax - bx, ay - by)


def normalize(x, y):
    d = math.hypot(x, y)

    if d < 1e-9:
        return 0.0, 0.0

    return x / d, y / d


def lerp(a, b, t):
    return a * (1.0 - t) + b * t


# ============================================================
# TRANSFORMATION
# ============================================================

class Transformation:

    def __init__(
        self,
        kind,
        x,
        y,
        actor,
        target=None,
        magnitude=1.0,
        time=0,
    ):
        self.kind = kind
        self.x = x
        self.y = y
        self.actor = actor
        self.target = target
        self.magnitude = magnitude
        self.time = time

    def spatial_key(self):
        return (
            self.kind,
            int(self.x // 70),
            int(self.y // 70),
        )


# ============================================================
# LAW
# ============================================================

class WorldLaw:

    def __init__(
        self,
        kind,
        x,
        y,
    ):
        self.kind = kind

        self.x = x
        self.y = y

        self.strength = 0.10
        self.energy = 0.0

        self.observations = 1
        self.age = 0

    def reinforce(
        self,
        x,
        y,
        amount=0.05,
    ):
        self.x = lerp(
            self.x,
            x,
            0.18,
        )

        self.y = lerp(
            self.y,
            y,
            0.18,
        )

        self.strength = clamp(
            self.strength + amount,
            0.0,
            1.0,
        )

        self.energy = clamp(
            self.energy + amount * 1.5,
            0.0,
            1.0,
        )

        self.observations += 1
        self.age = 0

    def decay(self):

        self.age += 1

        self.strength *= 0.999
        self.energy *= 0.997

    def alive(self):

        return (
            self.strength > 0.015
            or
            self.energy > 0.025
        )


# ============================================================
# META LAW
#
# Example:
#
#   SHOOT -> MISS
#   MISS  -> DASH
#   DASH  -> HIT
#
# This remembers changes between changes.
# ============================================================

class MetaLaw:

    def __init__(
        self,
        a,
        b,
    ):
        self.a = a
        self.b = b

        self.strength = 0.08
        self.count = 1
        self.age = 0

    def reinforce(self):

        self.count += 1

        self.strength = clamp(
            self.strength + 0.035,
            0,
            1,
        )

        self.age = 0

    def decay(self):

        self.age += 1
        self.strength *= 0.9992

    def alive(self):

        return self.strength > 0.018

    def key(self):

        return self.a, self.b


# ============================================================
# LAW GRAPH
# ============================================================

class LawGraph:

    def __init__(self):

        self.nodes = defaultdict(float)
        self.edges = defaultdict(float)

        self.history = defaultdict(
            lambda: deque(
                maxlen=40
            )
        )

    def observe(
        self,
        actor,
        event,
    ):

        self.nodes[event] += 1.0

        history = self.history[actor]

        if history:

            previous = history[-1]

            self.edges[
                previous,
                event,
            ] += 1.0

        history.append(event)

    def strongest_edges(
        self,
        n=10,
    ):

        return sorted(
            self.edges.items(),
            key=lambda x: x[1],
            reverse=True,
        )[:n]

    def count(self):

        return len(self.edges)

    def clear(self):

        self.nodes.clear()
        self.edges.clear()
        self.history.clear()


# ============================================================
# WORLD MEMORY
# ============================================================

class WorldMemory:

    def __init__(self):

        self.laws = []
        self.meta_laws = {}

        self.event_counts = defaultdict(int)

        self.recent_events = deque(
            maxlen=6000
        )

        self.last_event = {}

        self.world_energy = 0.0
        self.instability = 0.0

        self.load()

    # --------------------------------------------------------
    # OBSERVE
    # --------------------------------------------------------

    def observe(
        self,
        transformation,
    ):

        self.recent_events.append(
            transformation
        )

        self.world_energy = clamp(
            self.world_energy
            +
            0.004
            +
            0.001 *
            transformation.magnitude,
            0,
            1,
        )

        self.instability = clamp(
            self.instability
            +
            0.002
            +
            0.0015 *
            transformation.magnitude,
            0,
            1,
        )

        # ----------------------------------------------------
        # SPATIAL LAW
        # ----------------------------------------------------

        key = (
            transformation.spatial_key()
        )

        self.event_counts[key] += 1

        law = None

        for candidate in self.laws:

            if (
                candidate.kind
                != transformation.kind
            ):
                continue

            if (
                distance(
                    candidate.x,
                    candidate.y,
                    transformation.x,
                    transformation.y,
                )
                <
                LAW_RADIUS
            ):
                law = candidate
                break

        if law:

            law.reinforce(
                transformation.x,
                transformation.y,
                0.045,
            )

        elif (
            self.event_counts[key]
            >= LAW_THRESHOLD
            and
            len(self.laws)
            < MAX_LAWS
        ):

            self.laws.append(
                WorldLaw(
                    transformation.kind,
                    transformation.x,
                    transformation.y,
                )
            )

        # ----------------------------------------------------
        # META LAW
        # ----------------------------------------------------

        previous = self.last_event.get(
            transformation.actor
        )

        if (
            previous is not None
            and
            previous != transformation.kind
        ):

            meta_key = (
                previous,
                transformation.kind,
            )

            meta = self.meta_laws.get(
                meta_key
            )

            if meta:

                meta.reinforce()

            elif (
                len(
                    self.meta_laws
                )
                <
                MAX_META_LAWS
            ):

                self.meta_laws[
                    meta_key
                ] = MetaLaw(
                    previous,
                    transformation.kind,
                )

        self.last_event[
            transformation.actor
        ] = transformation.kind

    # --------------------------------------------------------
    # FIND LOCAL LAWS
    # --------------------------------------------------------

    def local_laws(
        self,
        x,
        y,
        radius=180,
    ):

        result = []

        for law in self.laws:

            d = distance(
                x,
                y,
                law.x,
                law.y,
            )

            if d < radius:

                result.append(
                    (
                        law,
                        d,
                    )
                )

        return result

    # --------------------------------------------------------
    # WORLD FIELD
    #
    # IMPORTANT:
    #
    # This is no longer a raw acceleration field.
    # It describes tendencies.
    # --------------------------------------------------------

    def field(
        self,
        x,
        y,
    ):

        danger = 0.0
        curvature = 0.0
        instability = 0.0

        left_bias = 0.0
        right_bias = 0.0

        up_bias = 0.0
        down_bias = 0.0

        for law, d in self.local_laws(
            x,
            y,
            190,
        ):

            if d < 1:

                falloff = 1.0

            else:

                falloff = (
                    1.0 -
                    d / 190.0
                )

            influence = (
                falloff
                *
                law.strength
                *
                (
                    0.35
                    +
                    0.65 *
                    law.energy
                )
            )

            # ------------------------------------------------
            # DANGER
            # ------------------------------------------------

            if law.kind in (
                "HIT",
                "BREAK",
                "COLLISION",
            ):

                danger += (
                    influence
                    *
                    0.42
                )

            elif law.kind == "MISS":

                danger += (
                    influence
                    *
                    0.08
                )

            # ------------------------------------------------
            # CURVATURE
            # ------------------------------------------------

            if law.kind in (
                "MISS",
                "SHOOT",
                "BOUNCE",
            ):

                curvature += (
                    influence
                    *
                    0.32
                )

            # ------------------------------------------------
            # INSTABILITY
            # ------------------------------------------------

            if law.kind in (
                "COLLISION",
                "HIT",
                "DASH",
            ):

                instability += (
                    influence
                    *
                    0.30
                )

            # ------------------------------------------------
            # SOFT PREFERENCE
            #
            # NOT a force.
            # Just a slight tendency.
            # ------------------------------------------------

            if law.kind == "DASH":

                if x > law.x:
                    right_bias += influence * 0.16
                else:
                    left_bias += influence * 0.16

            elif law.kind == "BOUNCE":

                if x > law.x:
                    left_bias += influence * 0.10
                else:
                    right_bias += influence * 0.10

            elif law.kind == "HIT":

                if y > law.y:
                    down_bias += influence * 0.08
                else:
                    up_bias += influence * 0.08

        # ----------------------------------------------------
        # META LAW
        # ----------------------------------------------------

        for meta in self.meta_laws.values():

            strength = meta.strength

            if (
                meta.a == "SHOOT"
                and
                meta.b == "MISS"
            ):

                curvature += (
                    strength * 0.24
                )

            elif (
                meta.a == "HIT"
                and
                meta.b == "DASH"
            ):

                instability += (
                    strength * 0.24
                )

            elif (
                meta.a == "MISS"
                and
                meta.b == "DASH"
            ):

                danger += (
                    strength * 0.08
                )

            elif (
                meta.a == "BOUNCE"
                and
                meta.b == "SHOOT"
            ):

                curvature += (
                    strength * 0.18
                )

        # ----------------------------------------------------
        # BALANCE
        #
        # Avoid directional runaway.
        # ----------------------------------------------------

        horizontal = (
            right_bias
            -
            left_bias
        )

        vertical = (
            up_bias
            -
            down_bias
        )

        horizontal = clamp(
            horizontal,
            -WORLD_STEER_LIMIT,
            WORLD_STEER_LIMIT,
        )

        vertical = clamp(
            vertical,
            -WORLD_STEER_LIMIT,
            WORLD_STEER_LIMIT,
        )

        return {
            "danger": clamp(
                danger,
                0,
                1,
            ),

            "curvature": clamp(
                curvature,
                0,
                1,
            ),

            "instability": clamp(
                instability,
                0,
                1,
            ),

            "horizontal": horizontal,
            "vertical": vertical,
        }

    # --------------------------------------------------------

    def danger(
        self,
        x,
        y,
    ):

        return self.field(
            x,
            y,
        )["danger"]

    def curvature(
        self,
        x,
        y,
    ):

        return self.field(
            x,
            y,
        )["curvature"]

    # --------------------------------------------------------
    # UPDATE
    # --------------------------------------------------------

    def update(self):

        self.world_energy *= 0.9996
        self.instability *= 0.997

        for law in self.laws:
            law.decay()

        self.laws = [
            law
            for law in self.laws
            if law.alive()
        ]

        for meta in self.meta_laws.values():
            meta.decay()

        self.meta_laws = {
            key: meta
            for key, meta
            in self.meta_laws.items()
            if meta.alive()
        }

    # --------------------------------------------------------

    def clear(self):

        self.laws.clear()
        self.meta_laws.clear()

        self.event_counts.clear()
        self.recent_events.clear()
        self.last_event.clear()

        self.world_energy = 0.0
        self.instability = 0.0

    # --------------------------------------------------------
    # SAVE
    # --------------------------------------------------------

    def save(self):

        data = {
            "laws": [],
            "meta_laws": [],
        }

        for law in self.laws:

            data["laws"].append({
                "kind": law.kind,
                "x": law.x,
                "y": law.y,
                "strength": law.strength,
                "energy": law.energy,
                "observations": law.observations,
                "age": law.age,
            })

        for meta in self.meta_laws.values():

            data["meta_laws"].append({
                "a": meta.a,
                "b": meta.b,
                "strength": meta.strength,
                "count": meta.count,
                "age": meta.age,
            })

        try:

            with open(
                MEMORY_FILE,
                "w",
                encoding="utf-8",
            ) as f:

                json.dump(
                    data,
                    f,
                    ensure_ascii=False,
                    indent=2,
                )

        except OSError:
            pass

    # --------------------------------------------------------
    # LOAD
    # --------------------------------------------------------

    def load(self):

        try:

            with open(
                MEMORY_FILE,
                "r",
                encoding="utf-8",
            ) as f:

                data = json.load(f)

            self.laws = []

            for item in data.get(
                "laws",
                [],
            ):

                law = WorldLaw(
                    item["kind"],
                    float(item["x"]),
                    float(item["y"]),
                )

                law.strength = float(
                    item.get(
                        "strength",
                        0.1,
                    )
                )

                law.energy = float(
                    item.get(
                        "energy",
                        0.0,
                    )
                )

                law.observations = int(
                    item.get(
                        "observations",
                        1,
                    )
                )

                law.age = int(
                    item.get(
                        "age",
                        0,
                    )
                )

                self.laws.append(law)

            self.meta_laws = {}

            for item in data.get(
                "meta_laws",
                [],
            ):

                a = item.get("a")
                b = item.get("b")

                if a is None or b is None:
                    continue

                meta = MetaLaw(
                    a,
                    b,
                )

                meta.strength = float(
                    item.get(
                        "strength",
                        0.08,
                    )
                )

                meta.count = int(
                    item.get(
                        "count",
                        1,
                    )
                )

                meta.age = int(
                    item.get(
                        "age",
                        0,
                    )
                )

                self.meta_laws[
                    (a, b)
                ] = meta

        except (
            OSError,
            json.JSONDecodeError,
            TypeError,
            ValueError,
            KeyError,
        ):

            self.laws = []
            self.meta_laws = {}


# ============================================================
# WORLD
# ============================================================

class World:

    def __init__(self):

        self.time = 0

        self.memory = WorldMemory()

        self.graph = TransformationGraph()

        self.zone = 0.0

        self.phase = "CALM"

        self.event_rate = 0.0

    # --------------------------------------------------------

    def field(
        self,
        x,
        y,
    ):

        return self.memory.field(
            x,
            y,
        )

    def danger(
        self,
        x,
        y,
    ):

        return self.memory.danger(
            x,
            y,
        )

    def curvature(
        self,
        x,
        y,
    ):

        return self.memory.curvature(
            x,
            y,
        )

    # --------------------------------------------------------

    def transform(
        self,
        kind,
        x,
        y,
        actor,
        target=None,
        magnitude=1.0,
    ):

        t = Transformation(
            kind,
            x,
            y,
            actor,
            target,
            magnitude,
            self.time,
        )

        self.memory.observe(t)

        self.graph.observe(
            actor,
            kind,
        )

        self.event_rate = (
            self.event_rate * 0.94
            +
            magnitude * 0.06
        )

        self.zone = clamp(
            self.zone
            +
            0.006
            +
            0.001 *
            magnitude,
            0,
            1,
        )

    # --------------------------------------------------------

    def update(self):

        self.time += 1

        self.zone *= 0.996

        self.event_rate *= 0.99

        self.memory.update()

        instability = (
            self.memory.instability
        )

        if instability < 0.15:

            self.phase = "CALM"

        elif instability < 0.40:

            self.phase = "ACTIVE"

        elif instability < 0.70:

            self.phase = "UNSTABLE"

        else:

            self.phase = "CHAOTIC"

        if (
            self.time % 450 == 0
        ):

            for fighter in fighters:

                if fighter.ai:

                    fighter.brain.replay()

        if (
            self.time % 900 == 0
        ):

            self.memory.save()


# ============================================================
# TRANSFORMATION GRAPH
# ============================================================

class TransformationGraph:

    def __init__(self):

        self.edges = defaultdict(int)
        self.last = {}

    def observe(
        self,
        actor,
        event,
    ):

        previous = self.last.get(
            actor
        )

        if (
            previous is not None
            and
            previous != event
        ):

            self.edges[
                previous,
                event,
            ] += 1

        self.last[actor] = event

    def strongest(self):

        if not self.edges:
            return None

        return max(
            self.edges.items(),
            key=lambda x: x[1],
        )

    def count(self):

        return len(self.edges)

    def clear(self):

        self.edges.clear()
        self.last.clear()


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
        vy,
    ):

        self.owner = owner

        self.x = x
        self.y = y

        self.vx = vx
        self.vy = vy

        self.life = BULLET_LIFE

        self.bounces = 0


# ============================================================
# OPPONENT MODEL
# ============================================================

class OpponentModel:

    def __init__(self):

        self.data = defaultdict(
            lambda: {
                "left": 0,
                "right": 0,
                "up": 0,
                "down": 0,
                "turn": 0,
                "last_x": None,
                "last_y": None,
                "last_vx": 0,
                "last_vy": 0,
            }
        )

    def observe(
        self,
        enemy,
    ):

        d = self.data[
            enemy.pid
        ]

        if d["last_x"] is not None:

            dx = (
                enemy.x -
                d["last_x"]
            )

            dy = (
                enemy.y -
                d["last_y"]
            )

            if abs(dx) > abs(dy):

                if dx > 0:
                    d["right"] += 1
                else:
                    d["left"] += 1

            else:

                if dy > 0:
                    d["up"] += 1
                else:
                    d["down"] += 1

            turn = (
                d["last_vx"] *
                enemy.vy
                -
                d["last_vy"] *
                enemy.vx
            )

            if abs(turn) > 2:
                d["turn"] += 1

        d["last_x"] = enemy.x
        d["last_y"] = enemy.y

        d["last_vx"] = enemy.vx
        d["last_vy"] = enemy.vy

    def horizontal_bias(
        self,
        pid,
    ):

        d = self.data[pid]

        total = (
            d["left"]
            +
            d["right"]
            +
            1
        )

        return (
            d["right"]
            -
            d["left"]
        ) / total


# ============================================================
# AI BRAIN
# ============================================================

class Brain:

    def __init__(
        self,
        pid,
        style,
    ):

        self.pid = pid
        self.style = style

        self.history = defaultdict(
            lambda: deque(
                maxlen=80
            )
        )

        self.opponents = OpponentModel()

        self.action_value = defaultdict(
            lambda:
            [0.0] * len(ACTIONS)
        )

        self.action_visits = defaultdict(
            lambda:
            [0] * len(ACTIONS)
        )

        self.experience = deque(
            maxlen=2000
        )

        self.prediction_error = 0.0

        self.curiosity = 0.8

        self.last_state = None
        self.last_action = None

        self.recent_actions = deque(
            maxlen=12
        )

    # --------------------------------------------------------
    # STATE
    # --------------------------------------------------------

    def state(
        self,
        me,
        target,
        world,
    ):

        if target is None:

            return (
                0, 0, 0,
                0,
                int(me.hp < 50),
                int(
                    world.danger(
                        me.x,
                        me.y,
                    )
                    > 0.5
                ),
            )

        d = distance(
            me.x,
            me.y,
            target.x,
            target.y,
        )

        field = world.field(
            me.x,
            me.y,
        )

        return (
            int(
                clamp(
                    (
                        target.x -
                        me.x
                    ) / 80,
                    -7,
                    7,
                )
            ),

            int(
                clamp(
                    (
                        target.y -
                        me.y
                    ) / 70,
                    -5,
                    5,
                )
            ),

            int(
                clamp(
                    (
                        target.vx -
                        me.vx
                    ) / 2.5,
                    -4,
                    4,
                )
            ),

            int(d > 300),

            int(me.hp // 20),

            int(target.hp // 20),

            int(
                field["danger"]
                > 0.5
            ),

            int(
                field["curvature"]
                > 0.35
            ),

            int(
                field["instability"]
                > 0.35
            ),
        )

    # --------------------------------------------------------
    # ENEMY OBSERVATION
    # --------------------------------------------------------

    def observe_enemy(
        self,
        enemy,
    ):

        history = self.history[
            enemy.pid
        ]

        if history:

            old = history[-1]

            predicted_x = (
                old[0]
                +
                old[2]
            )

            predicted_y = (
                old[1]
                +
                old[3]
            )

            error = distance(
                predicted_x,
                predicted_y,
                enemy.x,
                enemy.y,
            )

            self.prediction_error = (
                self.prediction_error
                * 0.965
                +
                min(
                    1.0,
                    error / 100,
                )
                * 0.035
            )

        history.append(
            (
                enemy.x,
                enemy.y,
                enemy.vx,
                enemy.vy,
            )
        )

        self.curiosity = clamp(
            0.25
            +
            self.prediction_error
            * 0.9,
            0.05,
            1.0,
        )

    # --------------------------------------------------------
    # PREDICT ENEMY
    # --------------------------------------------------------

    def predict_position(
        self,
        target,
        horizon,
    ):

        history = self.history[
            target.pid
        ]

        if len(history) < 3:

            return (
                target.x
                +
                target.vx *
                horizon,

                target.y
                +
                target.vy *
                horizon,
            )

        recent = list(
            history
        )[-8:]

        vx = (
            sum(
                item[2]
                for item in recent
            )
            /
            len(recent)
        )

        vy = (
            sum(
                item[3]
                for item in recent
            )
            /
            len(recent)
        )

        damp = clamp(
            1.0
            -
            self.prediction_error
            * 0.6,
            0.35,
            1.0,
        )

        bias = (
            self.opponents
            .horizontal_bias(
                target.pid
            )
        )

        return (
            target.x
            +
            vx *
            horizon *
            damp
            +
            bias *
            horizon
            *
            1.2,

            target.y
            +
            vy *
            horizon *
            damp,
        )

    # --------------------------------------------------------
    # AIM
    # --------------------------------------------------------

    def intercept(
        self,
        me,
        target,
    ):

        best = me.angle

        best_error = 1e9

        for horizon in (
            4, 6, 8,
            11, 14, 18,
        ):

            predicted = (
                self.predict_position(
                    target,
                    horizon,
                )
            )

            px, py = predicted

            angle = math.atan2(
                py - me.y,
                px - me.x,
            )

            future_x = (
                me.x
                +
                math.cos(angle)
                *
                BULLET_SPEED
                *
                horizon
            )

            future_y = (
                me.y
                +
                math.sin(angle)
                *
                BULLET_SPEED
                *
                horizon
            )

            error = distance(
                future_x,
                future_y,
                px,
                py,
            )

            if error < best_error:

                best_error = error
                best = angle

        return best

    # --------------------------------------------------------
    # WORLD PREDICTION
    #
    # Simulates intention, not raw physics.
    # --------------------------------------------------------

    def predict_world(
        self,
        me,
        action,
        world,
    ):

        px = me.x
        py = me.y

        vx = me.vx
        vy = me.vy

        future_danger = 0.0
        future_instability = 0.0

        for _ in range(8):

            field = world.field(
                px,
                py,
            )

            danger = field[
                "danger"
            ]

            instability = field[
                "instability"
            ]

            future_danger += danger
            future_instability += (
                instability
            )

            # ------------------------------------------------
            # ACTION INTENTION
            # ------------------------------------------------

            if action == "APPROACH":

                vx += 0.45

            elif action == "RETREAT":

                vx -= 0.45

            elif action == "STRAFE":

                vx += 0.12
                vy += 0.42

            elif action == "DASH":

                vx *= 1.10
                vy *= 1.10

            # ------------------------------------------------
            # WORLD PREFERENCE
            #
            # Very weak.
            # No accumulation monster.
            # ------------------------------------------------

            vx += (
                field["horizontal"]
                *
                0.08
            )

            vy += (
                field["vertical"]
                *
                0.08
            )

            vx *= 0.92
            vy *= 0.92

            vx = clamp(
                vx,
                -MAX_SPEED,
                MAX_SPEED,
            )

            vy = clamp(
                vy,
                -MAX_SPEED,
                MAX_SPEED,
            )

            px += vx * 0.20
            py += vy * 0.20

            px = clamp(
                px,
                LEFT + PLAYER_R,
                RIGHT - PLAYER_R,
            )

            py = clamp(
                py,
                BOTTOM + PLAYER_R,
                TOP - PLAYER_R,
            )

        return (
            px,
            py,
            future_danger / 8,
            future_instability / 8,
        )

    # --------------------------------------------------------
    # SCORE
    # --------------------------------------------------------

    def action_score(
        self,
        action,
        state,
        me,
        target,
        world,
    ):

        index = ACTIONS.index(
            action
        )

        visits = self.action_visits[
            state
        ][index]

        value = self.action_value[
            state
        ][index]

        exploration = (
            0.85
            /
            math.sqrt(
                visits + 1
            )
        )

        score = (
            value
            +
            exploration
            *
            (
                0.35
                +
                self.curiosity
            )
        )

        if target:

            d = distance(
                me.x,
                me.y,
                target.x,
                target.y,
            )

        else:

            d = 999

        local = world.field(
            me.x,
            me.y,
        )

        danger = local[
            "danger"
        ]

        # ----------------------------------------------------
        # BASIC TACTICS
        # ----------------------------------------------------

        if action == "APPROACH":

            score += (
                0.40
                if d > 250
                else -0.08
            )

        elif action == "RETREAT":

            score += (
                0.65
                if me.hp < 45
                else 0.04
            )

            score += (
                danger * 0.40
            )

        elif action == "STRAFE":

            score += (
                0.45
                if 130 < d < 420
                else 0.02
            )

        elif action == "HOLD":

            score += (
                0.32
                if 170 < d < 330
                else -0.06
            )

        elif action == "DASH":

            score += (
                0.70
                if danger > 0.55
                else 0.10
            )

        elif action == "SHOOT":

            score += (
                0.70
                if d < 500
                else -0.25
            )

            score += (
                0.22
                if self.prediction_error
                < 0.35
                else 0
            )

        # ----------------------------------------------------
        # PERSONALITY
        # ----------------------------------------------------

        if self.style == "aggressive":

            if action in (
                "APPROACH",
                "SHOOT",
            ):

                score += 0.20

        elif self.style == "tactical":

            if action in (
                "STRAFE",
                "RETREAT",
            ):

                score += 0.20

        elif self.style == "adaptive":

            if (
                self.last_action
                != action
            ):

                score += 0.12

        # ----------------------------------------------------
        # REPETITION PENALTY
        # ----------------------------------------------------

        if (
            len(
                self.recent_actions
            )
            >= 3
        ):

            recent = list(
                self.recent_actions
            )[-3:]

            if all(
                x == action
                for x in recent
            ):

                score -= 0.30

        # ----------------------------------------------------
        # FUTURE WORLD
        # ----------------------------------------------------

        (
            px,
            py,
            future_danger,
            future_instability,
        ) = self.predict_world(
            me,
            action,
            world,
        )

        score -= (
            future_danger
            *
            0.60
        )

        score -= (
            future_instability
            *
            0.20
        )

        # Shooting gains from stable curvature,
        # rather than raw force.

        if (
            action == "SHOOT"
            and
            target is not None
        ):

            curvature = local[
                "curvature"
            ]

            score += (
                curvature
                * 0.08
            )

        return score

    # --------------------------------------------------------
    # CHOOSE
    # --------------------------------------------------------

    def choose(
        self,
        me,
        target,
        world,
        fighters,
    ):

        for enemy in fighters:

            if (
                enemy.pid != me.pid
                and
                enemy.alive
            ):

                self.opponents.observe(
                    enemy
                )

                self.observe_enemy(
                    enemy
                )

        state = self.state(
            me,
            target,
            world,
        )

        scored = []

        for action in ACTIONS:

            score = self.action_score(
                action,
                state,
                me,
                target,
                world,
            )

            scored.append(
                (
                    score,
                    action,
                )
            )

        scored.sort(
            reverse=True
        )

        top = scored[:3]

        if random.random() < (
            0.05
            +
            0.15 *
            self.curiosity
        ):

            choice = random.choice(
                top
            )[1]

        else:

            choice = scored[0][1]

        self.last_state = state
        self.last_action = choice

        self.recent_actions.append(
            choice
        )

        return choice

    # --------------------------------------------------------
    # LEARN
    # --------------------------------------------------------

    def learn(
        self,
        reward,
        next_state,
    ):

        if (
            self.last_state is None
            or
            self.last_action is None
        ):

            return

        idx = ACTIONS.index(
            self.last_action
        )

        visits = self.action_visits[
            self.last_state
        ]

        values = self.action_value[
            self.last_state
        ]

        visits[idx] += 1

        alpha = (
            0.14
            if visits[idx] < 15
            else 0.05
        )

        future = (
            max(
                self.action_value[
                    next_state
                ]
            )
            if next_state
            else 0.0
        )

        target = (
            reward
            +
            0.82 *
            future
        )

        values[idx] += (
            alpha
            *
            (
                target
                -
                values[idx]
            )
        )

        self.experience.append(
            (
                self.last_state,
                self.last_action,
                reward,
                next_state,
            )
        )

    # --------------------------------------------------------

    def replay(self):

        if len(
            self.experience
        ) < 30:

            return

        data = list(
            self.experience
        )

        sample = random.sample(
            data,
            min(
                80,
                len(data),
            ),
        )

        for (
            state,
            action,
            reward,
            next_state,
        ) in sample:

            idx = ACTIONS.index(
                action
            )

            self.action_value[
                state
            ][idx] += (
                0.008 *
                reward
            )

    # --------------------------------------------------------

    def clear(self):

        self.history.clear()

        self.action_value.clear()
        self.action_visits.clear()

        self.experience.clear()
        self.recent_actions.clear()

        self.prediction_error = 0.0
        self.curiosity = 0.8

        self.last_state = None
        self.last_action = None


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
        style="tactical",
    ):

        self.pid = pid
        self.name = NAMES[pid]
        self.color = COLORS[pid]

        self.world = world

        self.ai = ai
        self.style = style

        self.spawn_x = x
        self.spawn_y = y

        self.brain = (
            Brain(
                pid,
                style,
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
            1.2,
        )

        self.reset()

    # --------------------------------------------------------

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

        self.bounce_lock = 0

        self.body.goto(
            self.x,
            self.y,
        )

    # --------------------------------------------------------

    @property
    def attack_power(self):

        return (
            1.0
            +
            (
                1.0
                -
                self.hp /
                MAX_HP
            )
            * 1.45
        )

    # --------------------------------------------------------

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

    # --------------------------------------------------------

    def target(
        self,
        fighters,
    ):

        enemies = [
            f
            for f in fighters
            if (
                f.pid != self.pid
                and
                f.alive
            )
        ]

        if not enemies:
            return None

        def score(enemy):

            d = distance(
                self.x,
                self.y,
                enemy.x,
                enemy.y,
            )

            low_hp_bonus = (
                30
                if enemy.hp < 35
                else 0
            )

            return (
                d
                +
                enemy.hp * 1.1
                -
                low_hp_bonus
            )

        return min(
            enemies,
            key=score,
        )

    # --------------------------------------------------------
    # AI
    # --------------------------------------------------------

    def ai_control(
        self,
        fighters,
    ):

        target = self.target(
            fighters
        )

        if target is None:

            return (
                0,
                0,
                False,
                False,
            )

        action = self.brain.choose(
            self,
            target,
            self.world,
            fighters,
        )

        self.last_action = action

        self.angle = (
            self.brain.intercept(
                self,
                target,
            )
        )

        dx = (
            target.x -
            self.x
        )

        dy = (
            target.y -
            self.y
        )

        nx, ny = normalize(
            dx,
            dy,
        )

        sx = -ny
        sy = nx

        d = distance(
            self.x,
            self.y,
            target.x,
            target.y,
        )

        mx = 0.0
        my = 0.0

        shoot = False
        dash = False

        if action == "APPROACH":

            mx, my = nx, ny

        elif action == "RETREAT":

            mx, my = -nx, -ny

        elif action == "STRAFE":

            mx = (
                sx
                +
                nx *
                0.12
            )

            my = (
                sy
                +
                ny *
                0.12
            )

        elif action == "HOLD":

            if d < 150:

                mx, my = -nx, -ny

            elif d > 330:

                mx, my = nx, ny

        elif action == "DASH":

            dash = (
                self.dash_cd <= 0
            )

            if self.hp < 35:

                mx, my = -nx, -ny

            else:

                mx, my = sx, sy

        elif action == "SHOOT":

            shoot = (
                self.cooldown <= 0
                and
                d < 550
            )

            mx, my = sx, sy

        # ----------------------------------------------------
        # SURVIVAL
        # ----------------------------------------------------

        danger = self.world.danger(
            self.x,
            self.y,
        )

        if danger > 0.78:

            # steer away from danger,
            # but do not teleport or add huge force.

            mx += -nx * 0.5
            my += -ny * 0.5

        if (
            self.hp < 20
            and
            d < 230
        ):

            mx = -nx
            my = -ny

            dash = (
                self.dash_cd <= 0
            )

        # ----------------------------------------------------
        # SHOOT CONFIDENCE
        # ----------------------------------------------------

        if (
            self.cooldown <= 0
            and
            d < 520
        ):

            if (
                self.brain.prediction_error
                < 0.45
                or
                target.hp < 35
            ):

                shoot = True

        return (
            mx,
            my,
            shoot,
            dash,
        )

    # --------------------------------------------------------
    # PLAYER
    # --------------------------------------------------------

    def user_control(
        self,
        keys,
    ):

        mx = (
            int(
                "right" in keys
                or
                "d" in keys
            )
            -
            int(
                "left" in keys
                or
                "a" in keys
            )
        )

        my = (
            int(
                "up" in keys
                or
                "w" in keys
            )
            -
            int(
                "down" in keys
                or
                "s" in keys
            )
        )

        if mx != 0 or my != 0:

            self.angle = math.atan2(
                my,
                mx,
            )

        return (
            mx,
            my,
            "shoot" in keys,
            "dash" in keys,
        )

    # --------------------------------------------------------
    # CONTROL
    # --------------------------------------------------------

    def control(
        self,
        fighters,
        keys,
    ):

        if not self.alive:
            return

        if self.ai:

            (
                mx,
                my,
                shoot,
                dash,
            ) = self.ai_control(
                fighters
            )

        else:

            (
                mx,
                my,
                shoot,
                dash,
            ) = self.user_control(
                keys
            )

        length = math.hypot(
            mx,
            my,
        )

        if length > 1:

            mx /= length
            my /= length

        # ----------------------------------------------------
        # PLAYER/AI INPUT
        # ----------------------------------------------------

        self.vx += (
            mx *
            MOVE_ACCEL
        )

        self.vy += (
            my *
            MOVE_ACCEL
        )

        # ----------------------------------------------------
        # VERY WEAK WORLD PREFERENCE
        #
        # This is intentionally NOT a force field.
        # ----------------------------------------------------

        field = self.world.field(
            self.x,
            self.y,
        )

        self.vx += (
            field["horizontal"]
            *
            0.10
        )

        self.vy += (
            field["vertical"]
            *
            0.10
        )

        # ----------------------------------------------------
        # DASH
        # ----------------------------------------------------

        if (
            dash
            and
            self.dash_cd <= 0
        ):

            self.vx += (
                math.cos(
                    self.angle
                )
                *
                DASH_POWER
            )

            self.vy += (
                math.sin(
                    self.angle
                )
                *
                DASH_POWER
            )

            self.dash_cd = (
                DASH_COOLDOWN
            )

            self.dashes += 1

            self.world.transform(
                "DASH",
                self.x,
                self.y,
                self.pid,
                magnitude=1.2,
            )

        # ----------------------------------------------------
        # PHYSICS
        # ----------------------------------------------------

        self.vx *= FRICTION
        self.vy *= FRICTION

        self.vx = clamp(
            self.vx,
            -MAX_SPEED,
            MAX_SPEED,
        )

        self.vy = clamp(
            self.vy,
            -MAX_SPEED,
            MAX_SPEED,
        )

        self.x += self.vx
        self.y += self.vy

        # ----------------------------------------------------
        # BOUNDARY
        # ----------------------------------------------------

        bounced = False

        if (
            self.x
            <
            LEFT + PLAYER_R
        ):

            self.x = (
                LEFT + PLAYER_R
            )

            self.vx = abs(
                self.vx
            )

            bounced = True

        elif (
            self.x
            >
            RIGHT - PLAYER_R
        ):

            self.x = (
                RIGHT - PLAYER_R
            )

            self.vx = -abs(
                self.vx
            )

            bounced = True

        if (
            self.y
            <
            BOTTOM + PLAYER_R
        ):

            self.y = (
                BOTTOM + PLAYER_R
            )

            self.vy = abs(
                self.vy
            )

            bounced = True

        elif (
            self.y
            >
            TOP - PLAYER_R
        ):

            self.y = (
                TOP - PLAYER_R
            )

            self.vy = -abs(
                self.vy
            )

            bounced = True

        if bounced:

            if self.bounce_lock <= 0:

                self.world.transform(
                    "BOUNCE",
                    self.x,
                    self.y,
                    self.pid,
                    magnitude=0.7,
                )

                self.bounce_lock = 18

        self.bounce_lock = max(
            0,
            self.bounce_lock - 1,
        )

        # ----------------------------------------------------
        # SHOOT
        # ----------------------------------------------------

        if (
            shoot
            and
            self.cooldown <= 0
        ):

            bullets.append(
                Bullet(
                    self.pid,

                    self.x
                    +
                    math.cos(
                        self.angle
                    )
                    *
                    21,

                    self.y
                    +
                    math.sin(
                        self.angle
                    )
                    *
                    21,

                    math.cos(
                        self.angle
                    )
                    *
                    BULLET_SPEED,

                    math.sin(
                        self.angle
                    )
                    *
                    BULLET_SPEED,
                )
            )

            self.cooldown = 11

            self.shots += 1

            self.world.transform(
                "SHOOT",
                self.x,
                self.y,
                self.pid,
                magnitude=0.5,
            )

        self.cooldown = max(
            0,
            self.cooldown - 1,
        )

        self.dash_cd = max(
            0,
            self.dash_cd - 1,
        )

    # --------------------------------------------------------
    # DAMAGE
    # --------------------------------------------------------

    def damage(
        self,
        amount,
        x,
        y,
        attacker,
    ):

        if not self.alive:
            return

        self.hp = max(
            0.0,
            self.hp - amount,
        )

        self.world.transform(
            "HIT",
            x,
            y,
            attacker,
            self.pid,
            amount,
        )

        if self.ai:

            self.brain.curiosity = clamp(
                self.brain.curiosity
                + 0.05,
                0.05,
                1.0,
            )

        if self.hp <= 0:

            self.alive = False

            self.world.transform(
                "BREAK",
                self.x,
                self.y,
                attacker,
                self.pid,
                magnitude=2.0,
            )


# ============================================================
# SCREEN
# ============================================================

screen = turtle.Screen()

screen.setup(
    SCREEN_W,
    SCREEN_H,
)

screen.bgcolor(
    "#070a12"
)

screen.title(
    "LAW OF CHANGE : EVOLVING WORLD v5"
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


# ============================================================
# GAME
# ============================================================

world = World()

fighters = [
    Fighter(
        0,
        -380,
        0,
        world,
        ai=False,
    ),

    Fighter(
        1,
        20,
        90,
        world,
        ai=True,
        style="aggressive",
    ),

    Fighter(
        2,
        380,
        -20,
        world,
        ai=True,
        style="adaptive",
    ),
]

bullets = []

keys = set()

paused = False


# ============================================================
# INPUT
# ============================================================

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
        key,
    )

    screen.onkeyrelease(
        lambda k=key.lower():
        key_up(k),
        key,
    )


screen.onkeypress(
    lambda:
    key_down("shoot"),
    "space",
)

screen.onkeyrelease(
    lambda:
    key_up("shoot"),
    "space",
)

screen.onkeypress(
    lambda:
    key_down("dash"),
    "Shift_L",
)

screen.onkeyrelease(
    lambda:
    key_up("dash"),
    "Shift_L",
)


# ============================================================
# DRAW
# ============================================================

def rect(
    turtle_obj,
    x1,
    y1,
    x2,
    y2,
    color,
    width=2,
):

    turtle_obj.color(color)
    turtle_obj.pensize(width)

    turtle_obj.goto(
        x1,
        y1,
    )

    turtle_obj.pendown()

    turtle_obj.goto(
        x2,
        y1,
    )

    turtle_obj.goto(
        x2,
        y2,
    )

    turtle_obj.goto(
        x1,
        y2,
    )

    turtle_obj.goto(
        x1,
        y1,
    )

    turtle_obj.penup()


def draw_world():

    draw.clear()

    border = (
        "#3b536b"
        if world.phase
        in ("CALM", "ACTIVE")
        else "#9a3d55"
    )

    rect(
        draw,
        LEFT,
        BOTTOM,
        RIGHT,
        TOP,
        border,
        3,
    )

    # --------------------------------------------------------
    # LAW MAP
    # --------------------------------------------------------

    for law in world.memory.laws:

        radius = (
            3
            +
            int(
                20 *
                law.strength
            )
        )

        color = {
            "HIT": "#ff405f",
            "DASH": "#687dff",
            "BOUNCE": "#ffbf55",
            "MISS": "#a56cff",
            "COLLISION": "#ffffff",
            "SHOOT": "#55eaff",
            "BREAK": "#ff8c42",
        }.get(
            law.kind,
            "#778399",
        )

        draw.goto(
            law.x,
            law.y,
        )

        draw.dot(
            radius,
            color,
        )

        # Weak halo only.
        if law.strength > 0.45:

            draw.pencolor(
                color
            )

            draw.pensize(1)

            draw.circle(
                radius * 2
            )

    # --------------------------------------------------------
    # WORLD CORE
    # --------------------------------------------------------

    if world.zone > 0.15:

        draw.goto(
            0,
            0,
        )

        draw.dot(
            35
            +
            int(
                95 *
                world.zone
            ),
            "#21131b",
        )

    # --------------------------------------------------------
    # BULLETS
    # --------------------------------------------------------

    for bullet in bullets:

        draw.goto(
            bullet.x,
            bullet.y,
        )

        draw.dot(
            7,
            COLORS[
                bullet.owner
            ],
        )

    # --------------------------------------------------------
    # FIGHTERS
    # --------------------------------------------------------

    for fighter in fighters:

        fighter.body.goto(
            fighter.x,
            fighter.y,
        )

        if not fighter.alive:

            draw.goto(
                fighter.x,
                fighter.y,
            )

            draw.dot(
                17,
                "#301822",
            )

            continue

        # name

        draw.goto(
            fighter.x,
            fighter.y + 28,
        )

        draw.color(
            fighter.color
        )

        draw.write(
            fighter.name,
            align="center",
            font=(
                "Arial",
                9,
                "bold",
            ),
        )

        # hp

        draw.color(
            fighter.color
        )

        draw.pensize(4)

        draw.goto(
            fighter.x - 22,
            fighter.y - 25,
        )

        draw.pendown()

        draw.goto(
            fighter.x
            -
            22
            +
            44 *
            fighter.hp /
            MAX_HP,

            fighter.y - 25,
        )

        draw.penup()

        # ai aim

        if fighter.ai:

            draw.color(
                fighter.color
            )

            draw.pensize(1)

            draw.goto(
                fighter.x,
                fighter.y,
            )

            draw.pendown()

            draw.goto(
                fighter.x
                +
                math.cos(
                    fighter.angle
                )
                *
                30,

                fighter.y
                +
                math.sin(
                    fighter.angle
                )
                *
                30,
            )

            draw.penup()


# ============================================================
# HUD
# ============================================================

def draw_hud():

    hud.clear()

    hud.goto(
        -545,
        330,
    )

    hud.color(
        "#e7edf7"
    )

    hud.write(
        "LAW OF CHANGE : EVOLVING WORLD v5",
        font=(
            "Arial",
            16,
            "bold",
        ),
    )

    strongest = (
        world.graph.strongest()
    )

    if strongest:

        chain = (
            f"{strongest[0][0]}"
            f"->{strongest[0][1]}"
            f" x{int(strongest[1])}"
        )

    else:

        chain = "---"

    hud.goto(
        -545,
        307,
    )

    hud.color(
        "#91a4c2"
    )

    hud.write(
        f"PHASE={world.phase:<8} "
        f"ENERGY={world.memory.world_energy:.2f} "
        f"INST={world.memory.instability:.2f} "
        f"LAWS={len(world.memory.laws):03d} "
        f"META={len(world.memory.meta_laws):03d} "
        f"GRAPH={world.graph.count():03d} "
        f"CHAIN={chain}",
        font=(
            "Consolas",
            9,
            "normal",
        ),
    )

    # --------------------------------------------------------
    # FIGHTER STATUS
    # --------------------------------------------------------

    y = 278

    for fighter in fighters:

        hud.goto(
            -545,
            y,
        )

        hud.color(
            fighter.color
        )

        if fighter.ai:

            brain = fighter.brain

            hud.write(
                f"{fighter.name:4} "
                f"HP={int(fighter.hp):3d} "
                f"{fighter.state():8} "
                f"ERR={brain.prediction_error:.2f} "
                f"CUR={brain.curiosity:.2f} "
                f"MEM={len(brain.experience):4d} "
                f"{fighter.last_action}",
                font=(
                    "Consolas",
                    9,
                    "normal",
                ),
            )

        else:

            hud.write(
                f"YOU  "
                f"HP={int(fighter.hp):3d} "
                f"{fighter.state():8} "
                f"ATK={fighter.attack_power:.2f}",
                font=(
                    "Consolas",
                    9,
                    "normal",
                ),
            )

        y -= 20

    # --------------------------------------------------------
    # META-LAWS
    # --------------------------------------------------------

    strongest_meta = sorted(
        world.memory.meta_laws.values(),
        key=lambda x:
        x.strength,
        reverse=True,
    )[:8]

    y = 180

    for meta in strongest_meta:

        hud.goto(
            700,
            y,
        )

        hud.color(
            "#7f8dac"
        )

        hud.write(
            f"{meta.a} -> {meta.b} "
            f"x{meta.count}",
            font=(
                "Consolas",
                8,
                "normal",
            ),
        )

        y -= 16

    # --------------------------------------------------------
    # WIN
    # --------------------------------------------------------

    alive = [
        fighter
        for fighter in fighters
        if fighter.alive
    ]

    if len(alive) == 1:

        hud.goto(
            0,
            -340,
        )

        hud.color(
            alive[0].color
        )

        hud.write(
            f"{alive[0].name} WINS",
            align="center",
            font=(
                "Arial",
                24,
                "bold",
            ),
        )

    # --------------------------------------------------------
    # CONTROLS
    # --------------------------------------------------------

    hud.goto(
        -545,
        -335,
    )

    hud.color(
        "#7e8aa0"
    )

    hud.write(
        "A/D or ←/→ move   "
        "W/S or ↑/↓ move/aim   "
        "SPACE shoot   "
        "SHIFT dash   "
        "R reset   E erase world   P pause",
        font=(
            "Arial",
            9,
            "normal",
        ),
    )


# ============================================================
# FIGHTER COLLISION
# ============================================================

def fighter_collision():

    for i in range(
        len(fighters)
    ):

        a = fighters[i]

        if not a.alive:
            continue

        for j in range(
            i + 1,
            len(fighters),
        ):

            b = fighters[j]

            if not b.alive:
                continue

            dx = (
                b.x -
                a.x
            )

            dy = (
                b.y -
                a.y
            )

            d = math.hypot(
                dx,
                dy,
            )

            minimum = (
                PLAYER_R * 2
            )

            if (
                0.001
                <
                d
                <
                minimum
            ):

                nx = dx / d
                ny = dy / d

                overlap = (
                    minimum -
                    d
                )

                a.x -= (
                    nx *
                    overlap *
                    0.5
                )

                a.y -= (
                    ny *
                    overlap *
                    0.5
                )

                b.x += (
                    nx *
                    overlap *
                    0.5
                )

                b.y += (
                    ny *
                    overlap *
                    0.5
                )

                rel = (
                    (b.vx - a.vx) * nx
                    +
                    (b.vy - a.vy) * ny
                )

                impulse = clamp(
                    rel * 0.65,
                    -3.0,
                    3.0,
                )

                a.vx += (
                    impulse * nx
                )

                a.vy += (
                    impulse * ny
                )

                b.vx -= (
                    impulse * nx
                )

                b.vy -= (
                    impulse * ny
                )

                world.transform(
                    "COLLISION",
                    (
                        a.x +
                        b.x
                    ) * 0.5,
                    (
                        a.y +
                        b.y
                    ) * 0.5,
                    a.pid,
                    b.pid,
                    magnitude=1.0,
                )


# ============================================================
# BULLET
# ============================================================

def update_bullets():

    survivors = []

    for bullet in bullets:

        field = world.field(
            bullet.x,
            bullet.y,
        )

        # ----------------------------------------------------
        # LAW CHANGES BULLET CURVATURE,
        # NOT ITS SPEED.
        # ----------------------------------------------------

        curvature = field[
            "curvature"
        ]

        speed = math.hypot(
            bullet.vx,
            bullet.vy,
        )

        if speed > 0:

            nx = (
                bullet.vx /
                speed
            )

            ny = (
                bullet.vy /
                speed
            )

            curvature_strength = (
                curvature *
                0.10
            )

            bullet.vx += (
                -ny *
                curvature_strength
            )

            bullet.vy += (
                nx *
                curvature_strength
            )

        # small damping prevents
        # runaway trajectory

        bullet.vx *= 0.995
        bullet.vy *= 0.995

        bullet.x += bullet.vx
        bullet.y += bullet.vy

        bullet.life -= 1

        hit = False

        # ----------------------------------------------------
        # WALL
        # ----------------------------------------------------

        if (
            bullet.x < LEFT
            or
            bullet.x > RIGHT
        ):

            bullet.x = clamp(
                bullet.x,
                LEFT,
                RIGHT,
            )

            bullet.vx *= -1

            bullet.bounces += 1

            world.transform(
                "BOUNCE",
                bullet.x,
                bullet.y,
                bullet.owner,
                magnitude=0.7,
            )

        if (
            bullet.y < BOTTOM
            or
            bullet.y > TOP
        ):

            bullet.y = clamp(
                bullet.y,
                BOTTOM,
                TOP,
            )

            bullet.vy *= -1

            bullet.bounces += 1

            world.transform(
                "BOUNCE",
                bullet.x,
                bullet.y,
                bullet.owner,
                magnitude=0.7,
            )

        # ----------------------------------------------------
        # HIT
        # ----------------------------------------------------

        for fighter in fighters:

            if not fighter.alive:
                continue

            if fighter.pid == bullet.owner:
                continue

            if (
                distance(
                    bullet.x,
                    bullet.y,
                    fighter.x,
                    fighter.y,
                )
                <
                PLAYER_R
                +
                BULLET_RADIUS
            ):

                attacker = fighters[
                    bullet.owner
                ]

                damage = (
                    7.0 *
                    attacker.attack_power
                )

                fighter.damage(
                    damage,
                    bullet.x,
                    bullet.y,
                    attacker.pid,
                )

                attacker.hits += 1

                world.transform(
                    "HIT",
                    bullet.x,
                    bullet.y,
                    attacker.pid,
                    fighter.pid,
                    magnitude=damage / 7.0,
                )

                hit = True

                break

        # ----------------------------------------------------
        # MISS / DESTROY
        # ----------------------------------------------------

        if not hit:

            if (
                bullet.life <= 0
                or
                bullet.bounces > 4
            ):

                world.transform(
                    "MISS",
                    bullet.x,
                    bullet.y,
                    bullet.owner,
                    magnitude=0.5,
                )

            else:

                survivors.append(
                    bullet
                )

    bullets[:] = survivors


# ============================================================
# RESET / ERASE
# ============================================================

def reset():

    for fighter in fighters:

        fighter.reset()

    bullets.clear()


def erase_world():

    world.memory.clear()

    world.graph.clear()

    for fighter in fighters:

        if fighter.ai:

            fighter.brain.clear()

    world.memory.save()


def toggle_pause():

    global paused

    paused = not paused


screen.onkey(
    reset,
    "r",
)

screen.onkey(
    erase_world,
    "e",
)

screen.onkey(
    toggle_pause,
    "p",
)

screen.listen()


# ============================================================
# MAIN LOOP
# ============================================================

def loop():

    if not paused:

        world.update()

        alive_count = sum(
            fighter.alive
            for fighter in fighters
        )

        if alive_count > 1:

            for fighter in fighters:

                fighter.control(
                    fighters,
                    keys,
                )

            fighter_collision()

            update_bullets()

    draw_world()

    draw_hud()

    screen.update()

    screen.ontimer(
        loop,
        FPS_MS,
    )


# ============================================================
# START
# ============================================================

loop()

turtle.done()
