# Bus Booking Service

REST API для бронирования автобусных билетов. Регистрация, поиск маршрутов, выбор места, подтверждение и отмена брони — всё через HTTP.

## Стек

| Слой | Технология |
|---|---|
| Фреймворк | FastAPI 0.115 + Uvicorn |
| База данных | PostgreSQL 16 + SQLAlchemy 2 (asyncpg) |
| Миграции | Alembic |
| Кэш | Redis 7 |
| Очереди | RabbitMQ 3.13 + FastStream |
| Аутентификация | JWT (python-jose + bcrypt) |
| Валидация | Pydantic v2 |
| Тесты | pytest + pytest-asyncio + httpx |

## Архитектура

```
app/
├── api/v1/          # HTTP-эндпоинты (auth, bookings, routes)
├── core/            # Конфигурация, JWT, rate limiting, обработка ошибок
├── db/              # Подключение к БД, сессии
├── models/          # SQLAlchemy-модели (User, Route, Seat, Booking)
├── repositories/    # Слой доступа к данным
├── schemas/         # Pydantic-схемы запросов и ответов
├── services/        # Бизнес-логика, кэш, брокер, воркер, уведомления
└── migration/       # Alembic-миграции
```

**Поток бронирования:**
1. Пользователь выбирает маршрут и место → `POST /bookings`
2. `BookingService` валидирует маршрут и место, создаёт бронь
3. Публикует событие `booking.confirmed` в RabbitMQ
4. Воркер получает событие → `NotificationService` отправляет письмо
5. При ошибке воркер делает до 3 повторных попыток, затем сообщение уходит в Dead Letter Queue

## Схема базы данных

```
users
├── id, email (unique), hashed_password
├── username, first_name, last_name
├── is_active, role (user | admin)
└── created_at

routes
├── id, origin, destination
├── departure_at, arrival_at
├── total_seats, price
└── is_active

seats
├── id, route_id → routes.id
├── seat_number
└── is_booked

bookings
├── id, user_id → users.id
├── route_id → routes.id, seat_id → seats.id (unique)
├── status (pending | confirmed | cancelled)
├── total_price
└── created_at, updated_at
```

## Быстрый старт

### Docker (рекомендуется)

```bash
# 1. Клонировать репозиторий
git clone <repo-url>
cd bus_booking_service

# 2. Скопировать и настроить переменные окружения
cp .env.example .env   # при необходимости отредактировать

# 3. Запустить все сервисы
docker compose up --build
```

API будет доступен на `http://localhost:8000`.  
Swagger UI: `http://localhost:8000/docs`  
RabbitMQ Management UI: `http://localhost:15672` (guest / guest)

### Локальный запуск

Требования: Python 3.12+, uv, запущенные PostgreSQL, Redis, RabbitMQ.

```bash
# Установить зависимости
uv sync

# Применить миграции
uv run alembic upgrade head

# Запустить сервер
uv run uvicorn app.main:app --reload --port 8000
```

### Запуск тестов

```bash
uv run pytest tests/ -v
```

Тесты используют SQLite in-memory и моки для Redis/RabbitMQ — внешние сервисы не нужны.

## Переменные окружения

Все переменные задаются в файле `.env`. Ниже полный список с описанием.

### Приложение

| Переменная | Пример | Описание |
|---|---|---|
| `PROJECT_NAME` | `Bus Booking Service` | Название в Swagger UI |
| `VERSION` | `1.0.0` | Версия API |
| `API_V1_STR` | `/api/v1` | Префикс всех эндпоинтов |

### PostgreSQL

| Переменная | Пример | Описание |
|---|---|---|
| `POSTGRES_HOST` | `postgres` | Хост БД (имя сервиса в Docker) |
| `POSTGRES_PORT` | `5432` | Порт |
| `POSTGRES_DB` | `booking_db` | Имя базы данных |
| `POSTGRES_USER` | `booking_user` | Пользователь |
| `POSTGRES_PASSWORD` | `booking_pass` | Пароль |

### Redis

| Переменная | Пример | Описание |
|---|---|---|
| `REDIS_HOST` | `redis` | Хост Redis |
| `REDIS_PORT` | `6379` | Порт |

### RabbitMQ

| Переменная | Пример | Описание |
|---|---|---|
| `RABBITMQ_HOST` | `rabbitmq` | Хост брокера |
| `RABBITMQ_PORT` | `5672` | AMQP-порт |
| `RABBITMQ_USER` | `guest` | Пользователь |
| `RABBITMQ_PASSWORD` | `guest` | Пароль |

### JWT

| Переменная | Пример | Описание |
|---|---|---|
| `SECRET_KEY` | `change-me-in-production` | **Обязательно сменить в продакшене** |
| `ALGORITHM` | `HS256` | Алгоритм подписи токена |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `60` | Время жизни токена в минутах |

### Rate Limiting

| Переменная | По умолчанию | Описание |
|---|---|---|
| `RATE_LIMIT_WINDOW_SECONDS` | `60` | Ширина скользящего окна |
| `RATE_LIMIT_AUTH` | `10` | Лимит для `/auth/login` и `/auth/register` |
| `RATE_LIMIT_BOOKINGS` | `20` | Лимит для `POST /bookings` |
| `RATE_LIMIT_DEFAULT` | `100` | Лимит для остальных эндпоинтов |

## API

Полная интерактивная документация доступна в Swagger UI по адресу `/docs`.

### Аутентификация

| Метод | Эндпоинт | Доступ | Описание |
|---|---|---|---|
| `POST` | `/api/v1/auth/register` | Публичный | Регистрация нового пользователя |
| `POST` | `/api/v1/auth/login` | Публичный | Получение JWT-токена |

### Маршруты

| Метод | Эндпоинт | Доступ | Описание |
|---|---|---|---|
| `GET` | `/api/v1/routes` | Публичный | Поиск маршрутов с фильтрацией и пагинацией |
| `POST` | `/api/v1/routes` | Только admin | Создание нового маршрута |
| `GET` | `/api/v1/routes/{id}/seats` | Публичный | Доступность мест на маршруте |

### Бронирования

| Метод | Эндпоинт | Доступ | Описание |
|---|---|---|---|
| `POST` | `/api/v1/bookings` | Авторизован | Забронировать место |
| `GET` | `/api/v1/bookings/my` | Авторизован | История броней текущего пользователя |
| `DELETE` | `/api/v1/bookings/{id}` | Авторизован | Отменить бронь |

### Прочее

| Метод | Эндпоинт | Описание |
|---|---|---|
| `GET` | `/api/v1/health` | Проверка работоспособности |

### Формат ошибок

Все ошибки возвращаются в едином формате:

```json
{
  "error": "Not Found",
  "detail": "Route not found or is inactive",
  "field": null
}
```

При ошибках валидации поле `field` содержит имя невалидного поля.

## Примеры запросов

### Регистрация

```bash
curl -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{
    "email": "user@example.com",
    "password": "secretpass",
    "username": "john",
    "first_name": "John",
    "last_name": "Doe"
  }'
```

### Логин и получение токена

```bash
curl -X POST http://localhost:8000/api/v1/auth/login \
  -F "username=user@example.com" \
  -F "password=secretpass"
```

Ответ:

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer"
}
```

### Поиск маршрутов

```bash
curl "http://localhost:8000/api/v1/routes?origin=Москва&destination=Сочи&page=1&size=10"
```

### Просмотр мест на маршруте

```bash
curl http://localhost:8000/api/v1/routes/1/seats
```

### Бронирование места

```bash
curl -X POST http://localhost:8000/api/v1/bookings \
  -H "Authorization: Bearer <token>" \
  -H "Content-Type: application/json" \
  -d '{"route_id": 1, "seat_id": 5}'
```

### Отмена брони

```bash
curl -X DELETE http://localhost:8000/api/v1/bookings/42 \
  -H "Authorization: Bearer <token>"
```

## Роли пользователей

| Роль | Возможности |
|---|---|
| `user` | Регистрация, поиск маршрутов, бронирование и отмена своих броней |
| `admin` | Всё что user + создание маршрутов |

Роль `admin` назначается напрямую в БД. Эндпоинт назначения ролей не предусмотрен.

## Кэширование

| Данные | TTL | Инвалидация |
|---|---|---|
| Список маршрутов | 30 сек | При создании нового маршрута |
| Места на маршруте | 15 сек | При бронировании или отмене |

## RabbitMQ топология

```
booking.events (topic exchange)
├── booking.confirmed.queue  ← routing key: booking.confirmed
│   └── on failure → booking.dlx
└── booking.cancelled.queue  ← routing key: booking.cancelled
    └── on failure → booking.dlx

booking.dlx (direct exchange)
└── booking.dlq  ← все провальные сообщения после 3 попыток
```

Воркер делает до **3 попыток** обработки с паузой 2 секунды между ними. При исчерпании попыток сообщение уходит в `booking.dlq` и логируется с уровнем `ERROR`.

## Структура проекта

```
.
├── app/
│   ├── api/v1/
│   │   ├── auth.py               # Регистрация и логин
│   │   ├── bookings.py           # CRUD бронирований
│   │   ├── routes_api.py         # Маршруты и места
│   │   └── health.py             # Health check
│   ├── core/
│   │   ├── config.py             # Настройки из .env
│   │   ├── security.py           # JWT, зависимости авторизации
│   │   ├── rate_limit.py         # Зависимости rate limiting
│   │   └── logging_config.py     # Конфигурация логов
│   ├── exception/
│   │   └── exception_handlers.py # Глобальные обработчики ошибок
│   ├── models/booking.py         # SQLAlchemy-модели
│   ├── repositories/             # Паттерн Repository
│   ├── schemas/                  # Pydantic-схемы
│   ├── services/
│   │   ├── booking_services.py   # Бизнес-логика бронирований
│   │   ├── broker.py             # RabbitMQ топология
│   │   ├── cache.py              # Redis-клиент
│   │   ├── notification.py       # Уведомления (email)
│   │   ├── rate_limiter.py       # Sliding window алгоритм
│   │   └── worker.py             # FastStream-подписчики
│   ├── migration/                # Alembic-миграции
│   └── main.py                   # Точка входа FastAPI
├── tests/
│   ├── integration/              # Тесты через HTTP-клиент
│   └── unit/                     # Юнит-тесты с моками
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── requirements.txt
```