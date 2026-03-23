from pydantic import BaseModel


class ErrorResponse(BaseModel):
    """Единый формат ошибки для всех эндпоинтов.

    Примеры:
        {"error": "Not Found", "detail": "Route not found or is inactive"}
        {"error": "Unprocessable Entity", "detail": "value is not a valid email address", "field": "email"}
    """

    error: str
    detail: str
    field: str | None = None
