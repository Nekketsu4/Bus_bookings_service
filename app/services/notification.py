"""
Сервис уведомлений.

Сейчас реализован как "structured stub" — правильный интерфейс,
реальная структура кода, логирование в формате который можно
подключить к email-провайдеру (SendGrid, SES, Postmark) одной заменой.

Чтобы подключить реальный email:
    1. pip install sendgrid  (или любой другой провайдер)
    2. Заменить тело _send_email на вызов провайдера
    3. Добавить SENDGRID_API_KEY в .env и Settings

Структура нарочно сделана так, чтобы эта замена была локальной —
никакие другие файлы менять не нужно.
"""

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class EmailMessage:
    """Структура email-сообщения."""

    to: str
    subject: str
    body: str


class NotificationService:
    """Отправляет уведомления пользователям о событиях бронирования."""

    async def send_booking_confirmed(
        self,
        user_email: str,
        booking_id: int,
        route: str,
    ) -> None:
        """Уведомление об успешном бронировании.

        Args:
            user_email: Email получателя.
            booking_id: ID бронирования для ссылки в письме.
            route:      Строка вида "Москва → Махачкала (01.06.2030 08:00)".
        """
        msg = EmailMessage(
            to=user_email,
            subject=f"Бронирование #{booking_id} подтверждено",
            body=(
                f"Ваше бронирование #{booking_id} успешно подтверждено.\n"
                f"Маршрут: {route}\n\n"
                f"Спасибо, что выбрали наш сервис!"
            ),
        )
        await self._send_email(msg)

    async def send_booking_cancelled(
        self,
        user_email: str,
        booking_id: int,
    ) -> None:
        """Уведомление об отмене бронирования.

        Args:
            user_email: Email получателя.
            booking_id: ID отменённого бронирования.
        """
        msg = EmailMessage(
            to=user_email,
            subject=f"Бронирование #{booking_id} отменено",
            body=(
                f"Ваше бронирование #{booking_id} было отменено.\n"
                f"Если вы не отменяли его — свяжитесь с поддержкой.\n\n"
                f"Возврат средств будет произведён в течение 3–5 рабочих дней."
            ),
        )
        await self._send_email(msg)

    async def _send_email(self, msg: EmailMessage) -> None:
        """Внутренний метод отправки.

        В текущей реализации логирует письмо структурированно —
        это удобно для локальной разработки и тестов.

        В продакшене замените тело на вызов реального провайдера:

            import sendgrid
            sg = sendgrid.SendGridAPIClient(api_key=settings.SENDGRID_API_KEY)
            sg.send(...)
        """
        logger.info(
            "[EMAIL] to=%s subject=%r body_length=%d",
            msg.to,
            msg.subject,
            len(msg.body),
        )
        # TODO: заменить на реального провайдера
        # await sendgrid_client.send(msg)


# Синглтон — создаётся один раз при импорте модуля.
# Если провайдер потребует инициализации (API-ключ, HTTP-сессия),
# создание перенесите в lifespan FastAPI.
notification_service = NotificationService()
