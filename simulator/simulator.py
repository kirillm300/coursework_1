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
POSTS = {
    'post_1': {'type': 'self_service', 'db_id': 1, 'brush_wear': 20.0, 'broken_cycles_left': 0},
    'post_2': {'type': 'robot',        'db_id': 2, 'brush_wear': 35.0, 'broken_cycles_left': 0}
}

# ========== СОСТОЯНИЕ ХИМИИ ==========
CHEMICALS = {
    'shampoo': 85.0,
    'wax':     70.0,
    'rinse':   90.0,
}

CHEMICAL_CONSUMPTION = {
    'shampoo': 0.8,
    'wax':     0.5,
    'rinse':   0.6,
}

# ========== ТАРИФЫ (загружаются из БД при старте) ==========
# Структура: {'self_service': [200.0, 300.0], 'robot': [400.0, 550.0]}
TARIFFS = {
    'self_service': [],
    'robot': []
}


class DatabaseManager:
    def __init__(self):
        self.conn = None
        self.lock = threading.Lock()

    @contextmanager
    def get_connection(self):
        conn = None
        try:
            conn = psycopg2.connect(**DB_CONFIG)
            yield conn
        except Exception as e:
            print(f"DB Error: {e}")
            yield None
        finally:
            if conn:
                conn.close()

    def load_tariffs(self):
        """Загружает актуальные тарифы из БД при старте симулятора"""
        with self.get_connection() as conn:
            if conn is None:
                print("⚠️ Не удалось загрузить тарифы из БД, используются значения по умолчанию")
                TARIFFS['self_service'] = [200.0, 300.0]
                TARIFFS['robot'] = [400.0, 550.0]
                return
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT s.post_type, t.price
                    FROM tariff t
                    JOIN service s ON t.service_id = s.service_id
                    WHERE t.valid_to IS NULL
                    ORDER BY s.post_type, t.price
                """)
                rows = cur.fetchall()
                for post_type, price in rows:
                    TARIFFS[post_type].append(float(price))

        print(f"Тарифы загружены из БД:")
        print(f"   self_service: {TARIFFS['self_service']} руб")
        print(f"   robot:        {TARIFFS['robot']} руб")

    def log_metric(self, post_id, metric_type_id, value):
        with self.lock:
            try:
                with self.get_connection() as conn:
                    if conn is None:
                        return
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
                    if conn is None:
                        return
                    with conn.cursor() as cur:
                        cur.execute("""
                            INSERT INTO incident (post_id, description, started_at, status)
                            VALUES (%s, %s, NOW(), 'open')
                        """, (post_id, description))
                        conn.commit()
            except Exception as e:
                print(f"Failed to log incident: {e}")


db = DatabaseManager()


def get_session_price(post_type: str) -> float:
    """Возвращает цену случайной услуги для данного типа поста"""
    prices = TARIFFS.get(post_type, [])
    if not prices:
        return 0.0
    return random.choice(prices)


def simulate_metrics():
    """Основной цикл симуляции"""
    last_minute = 0
    revenue_state = 0.0
    services_count = 0

    print("🚀 Simulation started")

    while True:
        current_minute = int(time.time() // 60)

        # ========== ОПЕРАЦИОННЫЕ МЕТРИКИ ==========

        q_self = random.randint(0, 6)
        q_robot = random.randint(0, 4)
        queue_length_self.set(q_self)
        queue_length_robot.set(q_robot)

        for post_id, post_info in POSTS.items():
            queue = q_self if post_info['type'] == 'self_service' else q_robot

            if post_info['broken_cycles_left'] > 0:
                status = 2
                post_info['broken_cycles_left'] -= 1
                if post_info['broken_cycles_left'] == 0:
                    print(f"🔧 {post_id} восстановлен после ремонта")

            elif queue > 0:
                status = random.choices([1, 2], weights=[95, 5])[0]
                if status == 2:
                    post_info['broken_cycles_left'] = random.randint(4, 20)
                    print(f"❌ {post_id} сломался, ремонт: {post_info['broken_cycles_left']} циклов")
                    db.log_incident(post_info['db_id'], f"Equipment failure on {post_id}")

            else:
                status = random.choices([0, 1, 2], weights=[50, 45, 5])[0]
                if status == 2:
                    post_info['broken_cycles_left'] = random.randint(4, 20)
                    print(f"❌ {post_id} сломался, ремонт: {post_info['broken_cycles_left']} циклов")
                    db.log_incident(post_info['db_id'], f"Equipment failure on {post_id}")

            post_status.labels(post_id=post_id).set(status)

            if status == 1:
                duration = random.randint(120, 600) if post_info['type'] == 'self_service' else random.randint(180, 400)
                session_duration.labels(post_id=post_id).set(duration)
            else:
                session_duration.labels(post_id=post_id).set(0)

        if current_minute != last_minute:
            for post_id in POSTS:
                cars_served_per_hour.labels(post_id=post_id).set(random.randint(3, 12))
            last_minute = current_minute

        # ========== ТЕХНИЧЕСКИЕ МЕТРИКИ ==========

        active_posts = sum(1 for p in POSTS.values() if p['broken_cycles_left'] == 0)
        for chem in CHEMICALS:
            consumption = CHEMICAL_CONSUMPTION[chem] * active_posts * random.uniform(0.5, 1.5)
            CHEMICALS[chem] = max(0.0, CHEMICALS[chem] - consumption)
            if CHEMICALS[chem] <= 15.0:
                CHEMICALS[chem] = random.uniform(85.0, 100.0)
                print(f"🧴 Химия '{chem}' пополнена до {CHEMICALS[chem]:.1f}%")
            chemical_level.labels(chemical_type=chem).set(CHEMICALS[chem])

        water_pressure.set(random.uniform(100, 160))
        pump_temperature.set(random.uniform(35, 65))

        if POSTS['post_2']['broken_cycles_left'] == 0:
            POSTS['post_2']['brush_wear'] += random.uniform(0.1, 0.8)
        if POSTS['post_2']['brush_wear'] >= 100.0:
            POSTS['post_2']['brush_wear'] = random.uniform(8.0, 15.0)
            print("🔧 Щётки поста 2 заменены")
        brush_wear.labels(post_id='post_2').set(POSTS['post_2']['brush_wear'])

        # ========== ФИНАНСОВЫЕ ==========
        # Завершение сессии — выручка считается по тарифам из БД
        for post_id, post_info in POSTS.items():
            # Сессия завершается только если пост был занят
            current_status = post_status.labels(post_id=post_id)._value.get()
            if current_status == 1 and random.random() < 0.3:
                price = get_session_price(post_info['type'])
                if price > 0:
                    revenue_state += price
                    services_count += 1
                    revenue_total.set(revenue_state)
                    services_completed.inc()
                    avg_check.set(revenue_state / services_count)
                    print(f"💰 {post_id}: сессия завершена, услуга {price:.0f} руб")

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
    # Загружаем тарифы из БД перед стартом симуляции
    db.load_tariffs()

    start_http_server(8000)
    print("Carwash Digital Twin Simulator started on port 8000")
    print("Metrics: http://localhost:8000/metrics")
    atexit.register(lambda: print("Simulator stopped"))
    simulate_metrics()