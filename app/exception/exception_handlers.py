import logging

from fastapi import FastAPI, HTTPException, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.schemas.error_schemas import ErrorResponse

logger = logging.getLogger(__name__)


# Словарь HTTP-статус → человекочитаемое название для поля "error"
_STATUS_NAMES: dict[int, str] = {
    400: "Bad Request",
    401: "Unauthorized",
    403: "Forbidden",
    404: "Not Found",
    409: "Conflict",
    422: "Unprocessable Entity",
    429: "Too Many Requests",
    500: "Internal Server Error",
}


def _error_name(status_code: int) -> str:
    return _STATUS_NAMES.get(status_code, "Error")


def register_exception_handlers(app: FastAPI):
    """Регистрируем глобально все обработчики исключений в приложении"""

    @app.exception_handler(HTTPException)
    async def http_exception_handler(
        request: Request, exc: HTTPException
    ) -> JSONResponse:
        """Перехватывапет все HTTPException и приводит к единому формату ErrorResponse"""
        return JSONResponse(
            status_code=exc.status_code,
            content=ErrorResponse(
                error=_error_name(exc.status_code),
                detail=exc.detail,
            ).model_dump(),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """
        Перехватывает ошибки валидации Pydantic (422).

        Берёт первую ошибку из списка, извлекает поле и сообщение.
        Это даёт клиенту конкретную информацию: какое поле невалидно и почему.
        """
        first_error = exc.errors()[0] if exc.errors() else {}

        # loc — список вида ("body", "email") или ("query", "page")
        # Берём последний элемент — это имя поля
        loc = first_error.get("loc", [])
        field = str(loc[-1]) if len(loc) > 1 else None
        detail = first_error.get("msg", "Validation error")

        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=ErrorResponse(
                error="Unprocessable Entity", detail=detail, field=field
            ).model_dump(),
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handlers(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Перехватывает все необработанные исключения.

        Логирует полный traceback на сервере (для отладки),
        но клиенту возвращает только общее сообщение — внутренние детали
        не должны утекать наружу (это и безопасность, и чистый API).
        """
        logger.exception(
            "Unhandled exception on %s %s",
            request.method,
            request.url.path,
            exc_info=exc,
        )
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content=ErrorResponse(
                error="Internal server error",
                detail="An unexpected error occorred. Please try again later.",
            ).model_dump(),
        )
