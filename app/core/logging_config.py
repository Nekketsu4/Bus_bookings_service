import logging.config

# ── Logging configuration ──────────────────────────────────────────────────────
# Настраиваем один раз при старте модуля.
# Формат: время | уровень | модуль | сообщение
logging.config.dictConfig(
    {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "default": {
                "format": "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": {
            "console": {
                "class": "logging.StreamHandler",
                "formatter": "default",
            },
        },
        "root": {
            "level": "INFO",
            "handlers": ["console"],
        },
        # Заглушаем шумные библиотеки
        "loggers": {
            "uvicorn.access": {"level": "WARNING"},
            "sqlalchemy.engine": {"level": "WARNING"},
        },
    }
)
