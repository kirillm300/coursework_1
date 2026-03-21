import time
import random
from prometheus_client import start_http_server, Gauge, Counter

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

POSTS = {
    'post_1': {'type': 'self_service', 'brush_wear': 20.0},
    'post_2': {'type': 'self_service'},
    'post_3': {'type': 'robot', 'brush_wear': 35.0},
    'post_4': {'type': 'robot', 'brush_wear': 28.0}
}

revenue_state = 0.0
services_count = 0

def simulate():
    global revenue_state, services_count
    
    while True:
        # Операционные метрики
        for post_id, post_info in POSTS.items():
            status = random.choices([0, 1, 2], weights=[40, 50, 10])[0]
            post_status.labels(post_id=post_id).set(status)
            
            if status == 1:
                duration = random.randint(120, 600) if post_info['type'] == 'self_service' else random.randint(180, 400)
                session_duration.labels(post_id=post_id).set(duration)
            else:
                session_duration.labels(post_id=post_id).set(0)
        
        queue_length_self.set(random.randint(0, 6))
        queue_length_robot.set(random.randint(0, 4))
        cars_served_per_hour.labels(post_id='post_1').set(random.randint(3, 12))
        
        # Технические метрики
        chemical_level.labels(chemical_type='shampoo').set(random.uniform(10, 100))
        chemical_level.labels(chemical_type='wax').set(random.uniform(20, 95))
        chemical_level.labels(chemical_type='rinse').set(random.uniform(15, 90))
        
        water_pressure.set(random.uniform(100, 160))
        pump_temperature.set(random.uniform(35, 65))
        
        # Износ щёток (роботы)
        for post_id in ['post_3', 'post_4']:
            POSTS[post_id]['brush_wear'] = min(POSTS[post_id]['brush_wear'] + random.uniform(0.1, 0.5), 100)
            brush_wear.labels(post_id=post_id).set(POSTS[post_id]['brush_wear'])
        
        # Финансовые
        if random.random() < 0.3:
            revenue_state += random.uniform(250, 650)
            services_count += 1
        revenue_total.set(revenue_state)
        services_completed.set(services_count)
        avg_check.set(revenue_state / max(services_count, 1))
        
        # Надёжность
        for post_id in POSTS:
            post_uptime.labels(post_id=post_id).set(random.uniform(97, 100))
        mttr_seconds.set(random.uniform(300, 1800))
        mtbf_hours.set(random.uniform(24, 168))
        monitoring_availability.set(99.9)
        
        time.sleep(15)

if __name__ == "__main__":
    start_http_server(8000)
    print("Carwash Digital Twin Simulator started!")
    simulate()
