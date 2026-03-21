import time
import random
import psycopg2
from prometheus_client import start_http_server, Gauge, Counter, Histogram
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

# Счётчики для расчётов
post_uptime_total = Counter('carwash_post_uptime_seconds_total', 'Total uptime seconds', ['post_id'])
post_total_seconds = Counter('carwash_post_total_seconds_total', 'Total seconds tracked', ['post_id'])

POSTS = {
    'post_1': {'type': 'self_service'},
    'post_2': {'type': 'self_service'}, 
    'post_3': {'type': 'robot'},
    'post_4': {'type': 'robot'}
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
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO metric_value (post_id, metric_type_id, value) 
                        VALUES (%s, %s, %s)
                    """, (post_id, metric_type_id, value))
                    conn.commit()
    
    def log_incident(self, post_id, description):
        with self.lock:
            with self.get_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("""
                        INSERT INTO incident (post_id, description, started_at, status)
                        VALUES (%s, %s, NOW(), 'open')
                    """, (post_id, description))
                    conn.commit()

db = DatabaseManager()

def simulate_metrics():
    """Основной цикл симуляции"""
    last_cars_served = {pid: 0 for pid in POSTS}
    last_minute = 0
    revenue_state = 0.0
    services_count = 0
    
    while True:
        current_minute = int(time.time() // 60)
        
        # ========== ОПЕРАЦИОННЫЕ МЕТРИКИ ==========
        # Статус постов
        for post_id in POSTS:
            status = random.choices([0, 1, 2], weights=[40, 50, 10])[0]
            post_status.labels(post_id=post_id).set(status)
            
            # Длительность сессии
            if status == 1:  # занят
                duration = random.randint(120, 600) if POSTS[post_id]['type'] == 'self_service' else random.randint(180, 400)
                session_duration.labels(post_id=post_id).set(duration)
            else:
                session_duration.labels(post_id=post_id).set(0)
        
        # Очереди
        queue_length_self.set(random.randint(0, 6))
        queue_length_robot.set(random.randint(0, 4))
        
        # Обслуженные за час
        if current_minute != last_minute:
            for post_id in POSTS:
                current_served = random.randint(3, 12)
                cars_served_per_hour.labels(post_id=post_id).set(current_served)
                last_cars_served[post_id] = current_served
            last_minute = current_minute
        
        # ========== ТЕХНИЧЕСКИЕ МЕТРИКИ ==========
        # Химия
        chemical_level.labels(chemical_type='shampoo').set(random.uniform(10, 100))
        chemical_level.labels(chemical_type='wax').set(random.uniform(20, 95))
        chemical_level.labels(chemical_type='rinse').set(random.uniform(15, 90))
        
        # Давление воды, температура насоса
        water_pressure.set(random.uniform(100, 160))
        pump_temperature.set(random.uniform(35, 65))
        
        # Износ щёток (только роботы)
        for post_id in ['post_3', 'post_4']:
            wear = POSTS[post_id].get('brush_wear', random.uniform(5, 80))
            wear += random.uniform(0.1, 0.8)
            wear = min(wear, 100)
            POSTS[post_id]['brush_wear'] = wear
            brush_wear.labels(post_id=post_id).set(wear)
        
        # ========== ФИНАНСОВЫЕ ==========
        if random.random() < 0.3:  # сессия завершилась
            revenue_state += random.uniform(250, 650)
            services_count += 1
            revenue_total.set(revenue_state)
            services_completed.inc()
            avg_check.set(revenue_state / max(services_count, 1))
        
        # ========== НАДЁЖНОСТЬ ==========
        # Uptime постов
        for post_id in POSTS:
            uptime_seconds = random.randint(3500, 3600)  # 97-100%
            post_uptime_total.labels(post_id=post_id).inc(uptime_seconds)
            post_total_seconds.labels(post_id=post_id).inc(3600)
            uptime_percent = (post_uptime_total.labels(post_id=post_id)._value.get() / 
                            post_total_seconds.labels(post_id=post_id)._value.get()) * 100
            post_uptime.labels(post_id=post_id).set(uptime_percent)
        
        # MTTR/MTBF - упрощённо
        mttr_seconds.set(random.uniform(300, 1800))
        mtbf_hours.set(random.uniform(24, 168))
        monitoring_availability.set(random.uniform(99.5, 100))
        
        # ========== ЗАПИСЬ В БД ==========
        # Метрики в БД (пример для нескольких типов)
        db.log_metric(1, 1, queue_length_self._value.get())  # queue_length
        db.log_metric(3, 2, session_duration.labels(post_id='post_3')._value.get())  # session_duration
        
        # Случайные инциденты
        if random.random() < 0.02:  # 2% шанс
            incident_post = random.choice(list(POSTS.keys()))
            description = f"Technical failure on {incident_post}"
            db.log_incident(post_id=1 if 'post_1' in incident_post else 3, description=description)
        
        time.sleep(15)

if __name__ == "__main__":
    start_http_server(8000)
    print("Carwash Digital Twin Simulator started on port 8000")
    print("Metrics available at http://localhost:8000/metrics")
    atexit.register(lambda: print("Simulator stopped"))
    simulate_metrics()
