import time
import random
import psycopg2
from prometheus_client import start_http_server, Gauge, Counter
from contextlib import contextmanager
import threading
import atexit

# ========== НАСТРОЙКИ ПОДКЛЮЧЕНИЯ К БД ==========
DB_CONFIG = {
    'host': 'postgres',
    'database': 'carwash',
    'user': 'carwash_user',
    'password': 'carwash_pass',
    'port': 5432
}

# ========== PROMETHEUS МЕТРИКИ ==========
# Операционные
post_status = Gauge('carwash_post_status', 'Post status: 0=free, 1=busy, 2=broken', ['post_id'])
queue_length_self = Gauge('carwash_queue_length_self_service', 'Queue length for self-service posts')
queue_length_robot = Gauge('carwash_queue_length_robot', 'Queue length for robot posts')
session_duration = Gauge('carwash_session_duration_seconds', 'Current session duration', ['post_id'])
cars_served_per_hour = Gauge('carwash_cars_served_per_hour', 'Cars served per hour', ['post_id'])

# Технические
chemical_level = Gauge('carwash_chemical_level_percent', 'Chemical level %', ['chemical_type'])
water_pressure = Gauge('carwash_water_pressure_bar', 'Water pressure in bar')
brush_wear = Gauge('carwash_brush_wear_percent', 'Brush wear %', ['post_id'])
pump_temperature = Gauge('carwash_pump_temperature_celsius', 'Pump temperature °C')

# Финансовые
revenue_total = Gauge('carwash_revenue_total_rub', 'Total revenue RUB')
services_completed = Counter('carwash_services_completed_total', 'Total completed services')
avg_check = Gauge('carwash_avg_check_rub', 'Average check RUB')

# Надёжность
post_uptime = Gauge('carwash_post_uptime_percent', 'Post uptime %', ['post_id'])
mttr_seconds = Gauge('carwash_mttr_seconds', 'Mean Time To Recovery seconds')
mtbf_hours = Gauge('carwash_mtbf_hours', 'Mean Time Between Failures hours')
monitoring_availability = Gauge('carwash_monitoring_availability_percent', 'Monitoring system availability %')

# ========== СОСТОЯНИЕ ПОСТОВ ==========
# broken_cycles_left — сколько циклов пост ещё будет сломан (0 = работает)
POSTS = {
    'post_1': {'type': 'self_service', 'brush_wear': 20.0, 'broken_cycles_left': 0},
    'post_2': {'type': 'robot',        'brush_wear': 35.0, 'broken_cycles_left': 0}
}

# ========== СОСТОЯНИЕ ХИМИИ ==========
# Химия постепенно расходуется и пополняется при достижении минимума
CHEMICALS = {
    'shampoo': 85.0,
    'wax':     70.0,
    'rinse':   90.0,
}

# Скорость расхода за цикл на один активный пост
CHEMICAL_CONSUMPTION = {
    'shampoo': 0.8,
    'wax':     0.5,
    'rinse':   0.6,
}

class DatabaseManager:
    def __init__(self):
        self.conn = None
        self.lock = threading.Lock()

    @contextmanager
    def get_connection(self):
        try:
            self.conn = psycopg2.connect(**DB_CONFIG)
            yield self.conn
        except Exception as e:
            print(f"DB Error: {e}")
        finally:
            if self.conn:
                self.conn.close()
                self.conn = None

    def log_metric(self, post_id, metric_type_id, value):
        with self.lock:
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO metric_value (post_id, metric_type_id, value)
                            VALUES (%s, %s, %s)
                        """, (post_id, metric_type_id, value))
                        conn.commit()
            except Exception as e:
                print(f"Failed to log metric: {e}")

    def log_incident(self, post_id, description):
        with self.lock:
            try:
                with self.get_connection() as conn:
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO incident (post_id, description, started_at, status)
                            VALUES (%s, %s, NOW(), 'open')
                        """, (post_id, description))
                        conn.commit()
            except Exception as e:
                print(f"Failed to log incident: {e}")

db = DatabaseManager()

def simulate_metrics():
    """Основной цикл симуляции"""
    last_minute = 0
    revenue_state = 0.0
    services_count = 0

    print("Simulation started")

    while True:
        current_minute = int(time.time() // 60)

        # ========== ОПЕРАЦИОННЫЕ МЕТРИКИ ==========

        # Сначала генерируем очереди
        q_self = random.randint(0, 6)
        q_robot = random.randint(0, 4)
        queue_length_self.set(q_self)
        queue_length_robot.set(q_robot)

        # Статус поста зависит от очереди и состояния поломки
        for post_id, post_info in POSTS.items():
            queue = q_self if post_info['type'] == 'self_service' else q_robot

            if post_info['broken_cycles_left'] > 0:
                # Пост сломан — остаётся сломанным, уменьшаем счётчик
                status = 2
                post_info['broken_cycles_left'] -= 1
                if post_info['broken_cycles_left'] == 0:
                    print(f"🔧 {post_id} восстановлен после ремонта")

            elif queue > 0:
                # Есть очередь — пост занят, с малым шансом сломаться
                status = random.choices([1, 2], weights=[95, 5])[0]
                if status == 2:
                    # Поломка — пост будет сломан 4-20 циклов (1-5 минут)
                    post_info['broken_cycles_left'] = random.randint(4, 20)
                    print(f"❌ {post_id} сломался, ремонт займёт {post_info['broken_cycles_left']} циклов")
                    db.log_incident(
                        1 if post_id == 'post_1' else 2,
                        f"Equipment failure on {post_id}"
                    )

            else:
                # Очереди нет — пост свободен или занят, редко ломается
                status = random.choices([0, 1, 2], weights=[50, 45, 5])[0]
                if status == 2:
                    post_info['broken_cycles_left'] = random.randint(4, 20)
                    print(f"❌ {post_id} сломался, ремонт займёт {post_info['broken_cycles_left']} циклов")
                    db.log_incident(
                        1 if post_id == 'post_1' else 2,
                        f"Equipment failure on {post_id}"
                    )

            post_status.labels(post_id=post_id).set(status)

            # Длительность сессии только если занят
            if status == 1:
                duration = random.randint(120, 600) if post_info['type'] == 'self_service' else random.randint(180, 400)
                session_duration.labels(post_id=post_id).set(duration)
            else:
                session_duration.labels(post_id=post_id).set(0)

        # Обслуженные за час (обновляем раз в минуту)
        if current_minute != last_minute:
            for post_id in POSTS:
                current_served = random.randint(3, 12)
                cars_served_per_hour.labels(post_id=post_id).set(current_served)
            last_minute = current_minute

        # ========== ТЕХНИЧЕСКИЕ МЕТРИКИ ==========

        # Химия — постепенный расход, пополнение при достижении минимума
        active_posts = sum(
            1 for p in POSTS.values()
            if p['broken_cycles_left'] == 0
        )
        for chem in CHEMICALS:
            consumption = CHEMICAL_CONSUMPTION[chem] * active_posts * random.uniform(0.5, 1.5)
            CHEMICALS[chem] = max(0.0, CHEMICALS[chem] - consumption)

            # Пополнение при достижении 15% — имитация заправки
            if CHEMICALS[chem] <= 15.0:
                CHEMICALS[chem] = random.uniform(85.0, 100.0)
                print(f"🧴 Химия '{chem}' пополнена до {CHEMICALS[chem]:.1f}%")

            chemical_level.labels(chemical_type=chem).set(CHEMICALS[chem])

        # Давление воды, температура насоса (общие для всей мойки)
        water_pressure.set(random.uniform(100, 160))
        pump_temperature.set(random.uniform(35, 65))

        # Износ щёток (только робот post_2)
        # Расходуется только если пост работает
        if POSTS['post_2']['broken_cycles_left'] == 0:
            POSTS['post_2']['brush_wear'] += random.uniform(0.1, 0.8)

        # При достижении 100% — имитация замены щёток
        if POSTS['post_2']['brush_wear'] >= 100.0:
            POSTS['post_2']['brush_wear'] = random.uniform(8.0, 15.0)
            print("🔧 Щётки поста 2 заменены")

        brush_wear.labels(post_id='post_2').set(POSTS['post_2']['brush_wear'])

        # ========== ФИНАНСОВЫЕ ==========
        if random.random() < 0.3:  # сессия завершилась
            revenue_state += random.uniform(250, 650)
            services_count += 1
            revenue_total.set(revenue_state)
            services_completed.inc()
            avg_check.set(revenue_state / max(services_count, 1))

        # ========== НАДЁЖНОСТЬ ==========
        for post_id in POSTS:
            post_uptime.labels(post_id=post_id).set(random.uniform(97, 100))
        mttr_seconds.set(random.uniform(300, 1800))
        mtbf_hours.set(random.uniform(24, 168))
        monitoring_availability.set(random.uniform(99.5, 100))

        # ========== ЗАПИСЬ В БД ==========
        try:
            db.log_metric(1, 1, queue_length_self._value.get())
            db.log_metric(2, 2, session_duration.labels(post_id='post_2')._value.get())
        except Exception as e:
            print(f"DB log error: {e}")

        time.sleep(15)

if __name__ == "__main__":
    start_http_server(8000)
    print("Carwash Digital Twin Simulator started on port 8000")
    print("Metrics: http://localhost:8000/metrics")
    atexit.register(lambda: print("Simulator stopped"))
    simulate_metrics()