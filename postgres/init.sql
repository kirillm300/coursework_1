-- =====================
-- ENUM типы
-- =====================
CREATE TYPE post_type_enum AS ENUM ('robot', 'self_service');
CREATE TYPE incident_status_enum AS ENUM ('open', 'closed');
CREATE TYPE metric_group_enum AS ENUM ('operational', 'technical', 'financial', 'reliability');

-- =====================
-- Пост автомойки
-- =====================
CREATE TABLE IF NOT EXISTS post (
    post_id     SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    post_type   post_type_enum NOT NULL,
    description TEXT
);

-- =====================
-- Вид услуги
-- =====================
CREATE TABLE IF NOT EXISTS service (
    service_id  SERIAL PRIMARY KEY,
    name        VARCHAR(100) NOT NULL,
    post_type   post_type_enum NOT NULL,
    description TEXT
);

-- =====================
-- Связь поста и услуги (многие ко многим)
-- =====================
CREATE TABLE IF NOT EXISTS post_service (
    post_id     INTEGER REFERENCES post(post_id),
    service_id  INTEGER REFERENCES service(service_id),
    PRIMARY KEY (post_id, service_id)
);

-- =====================
-- Тариф
-- =====================
CREATE TABLE IF NOT EXISTS tariff (
    tariff_id   SERIAL PRIMARY KEY,
    service_id  INTEGER NOT NULL REFERENCES service(service_id),
    price       NUMERIC(10,2) NOT NULL CHECK (price > 0),
    unit        VARCHAR(30) NOT NULL,
    valid_from  DATE NOT NULL,
    valid_to    DATE CHECK (valid_to IS NULL OR valid_to > valid_from)
);

-- =====================
-- Тип метрики
-- =====================
CREATE TABLE IF NOT EXISTS metric_type (
    metric_type_id  SERIAL PRIMARY KEY,
    name            VARCHAR(100) NOT NULL UNIQUE,
    unit            VARCHAR(30) NOT NULL,
    group_name      metric_group_enum NOT NULL,
    description     TEXT
);

-- =====================
-- Значение метрики
-- =====================
CREATE TABLE IF NOT EXISTS metric_value (
    metric_value_id BIGSERIAL PRIMARY KEY,
    post_id         INTEGER NOT NULL REFERENCES post(post_id),
    metric_type_id  INTEGER NOT NULL REFERENCES metric_type(metric_type_id),
    value           NUMERIC(12,4) NOT NULL,
    recorded_at     TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- =====================
-- Инцидент
-- =====================
CREATE TABLE IF NOT EXISTS incident (
    incident_id SERIAL PRIMARY KEY,
    post_id     INTEGER NOT NULL REFERENCES post(post_id),
    description TEXT,
    started_at  TIMESTAMPTZ NOT NULL,
    resolved_at TIMESTAMPTZ,
    status      incident_status_enum NOT NULL
);

-- =====================
-- Начальные данные
-- =====================

-- Посты (2 поста: самообслуживание и робот)
INSERT INTO post (name, post_type, description) VALUES
    ('Пост 1', 'self_service', 'Пост самообслуживания'),
    ('Пост 2', 'robot',        'Роботизированный пост');

-- Услуги
INSERT INTO service (name, post_type, description) VALUES
    ('Базовая мойка',       'self_service', 'Мойка кузова вручную'),
    ('Мойка с пеной',       'self_service', 'Мойка с нанесением пены'),
    ('Стандартная мойка',   'robot',        'Автоматическая мойка кузова'),
    ('Мойка с воском',      'robot',        'Автоматическая мойка с нанесением воска');

-- Связь постов и услуг
INSERT INTO post_service (post_id, service_id) VALUES
    (1, 1), (1, 2),   -- Пост 1 (self_service): базовая мойка + мойка с пеной
    (2, 3), (2, 4);   -- Пост 2 (robot): стандартная мойка + мойка с воском

-- Тарифы
INSERT INTO tariff (service_id, price, unit, valid_from) VALUES
    (1, 200.00, 'за сессию', '2025-01-01'),
    (2, 300.00, 'за сессию', '2025-01-01'),
    (3, 400.00, 'за сессию', '2025-01-01'),
    (4, 550.00, 'за сессию', '2025-01-01');

-- Типы метрик
INSERT INTO metric_type (name, unit, group_name, description) VALUES
    ('queue_length',            'шт',   'operational',  'Количество машин в очереди'),
    ('session_duration',        'сек',  'operational',  'Длительность сессии мойки'),
    ('chemical_shampoo',        'л',    'technical',    'Остаток шампуня'),
    ('chemical_wax',            'л',    'technical',    'Остаток воска'),
    ('chemical_rinse',          'л',    'technical',    'Остаток ополаскивателя'),
    ('chemical_foam',           'л',    'technical',    'Остаток пены'),
    ('water_consumption',       'л/ч',  'technical',    'Расход воды'),
    ('revenue',                 'руб',  'financial',    'Выручка'),
    ('brush_wear',              '%',    'reliability',  'Износ щёток'),
    ('downtime',                'сек',  'reliability',  'Время простоя'),
    ('error_count',             'шт',   'reliability',  'Количество ошибок');