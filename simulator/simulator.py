import time
import random
from prometheus_client import start_http_server, Gauge, Counter

# ---------- Очередь и посты ----------
queue_length = Gauge(
    "carwash_queue_length",
    "Number of cars waiting in queue"
)

post_status = Gauge(
    "carwash_post_status",
    "Post status: 0=free, 1=busy, 2=error",
    ["post_id", "post_type"]
)

# ---------- Сессии ----------
session_duration = Gauge(
    "carwash_session_duration_seconds",
    "Duration of current wash session",
    ["post_id"]
)

cars_served = Counter(
    "carwash_cars_served_total",
    "Total cars served since start",
    ["post_id"]
)

# ---------- Химия ----------
chemical_remaining = Gauge(
    "carwash_chemical_remaining_liters",
    "Remaining chemical level in liters",
    ["chemical_type"]
)

# ---------- Вода ----------
water_consumption = Gauge(
    "carwash_water_consumption_liters",
    "Water consumption per hour"
)

# ---------- Простои и ошибки ----------
downtime = Gauge(
    "carwash_downtime_seconds",
    "Current downtime duration in seconds",
    ["post_id"]
)

error_count = Counter(
    "carwash_error_count_total",
    "Total errors per post",
    ["post_id"]
)

# ---------- Износ щёток (только роботы) ----------
brush_wear = Gauge(
    "carwash_brush_wear_percent",
    "Brush wear percentage (robot posts only)",
    ["post_id"]
)

# ---------- Выручка ----------
revenue = Gauge(
    "carwash_revenue_total",
    "Total revenue in rubles"
)

POSTS = [
    {"id": "post_1", "type": "self_service"},
    {"id": "post_2", "type": "self_service"},
    {"id": "post_3", "type": "robot"},
    {"id": "post_4", "type": "robot"},
]

def simulate():
    # Инициализация износа щёток
    brush_wear_state = {"post_3": 20.0, "post_4": 35.0}
    revenue_state = 0.0

    while True:
        # Очередь
        queue_length.set(random.randint(0, 8))

        for post in POSTS:
            pid = post["id"]
            ptype = post["type"]

            # Статус поста
            status = random.choices([0, 1, 2], weights=[30, 60, 10])[0]
            post_status.labels(post_id=pid, post_type=ptype).set(status)

            # Длительность сессии
            if status == 1:
                duration = random.randint(120, 600) if ptype == "self_service" else random.randint(180, 300)
                session_duration.labels(post_id=pid).set(duration)
                cars_served.labels(post_id=pid).inc()
                revenue_state += random.uniform(200, 600)
            else:
                session_duration.labels(post_id=pid).set(0)

            # Простой
            if status == 0:
                downtime.labels(post_id=pid).set(random.randint(0, 300))
            else:
                downtime.labels(post_id=pid).set(0)

            # Ошибки
            if status == 2:
                error_count.labels(post_id=pid).inc()

            # Износ щёток для роботов
            if ptype == "robot":
                brush_wear_state[pid] = min(brush_wear_state[pid] + random.uniform(0.1, 0.5), 100.0)
                brush_wear.labels(post_id=pid).set(brush_wear_state[pid])

        # Химия
        chemical_remaining.labels(chemical_type="shampoo").set(random.uniform(5, 100))
        chemical_remaining.labels(chemical_type="wax").set(random.uniform(5, 100))
        chemical_remaining.labels(chemical_type="rinse").set(random.uniform(5, 100))
        chemical_remaining.labels(chemical_type="foam").set(random.uniform(5, 100))

        # Вода и выручка
        water_consumption.set(random.uniform(50, 300))
        revenue.set(revenue_state)

        time.sleep(15)

if __name__ == "__main__":
    start_http_server(8000)
    print("Simulator started on port 8000")
    simulate()
