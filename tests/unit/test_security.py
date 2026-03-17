import pytest
from fastapi import HTTPException

from app.core.security import (
    create_access_token,
    hash_password,
    verify_password,
    get_current_user_id,
)

def test_hash_and_verify_password():
    """
    Проверяем что переданный пароль корректно
    хэшируется и затем корректно выполняет
    проверку этого захешированного пароля
    """
    plain = "mysecretpassword"
    hashed = hash_password(plain)
    assert hashed != plain
    assert verify_password(plain, hashed)


def test_create_and_decode_token():
    """
    Проверяем что корректно создается JWT токен
    с переданным payload
    """
    token = create_access_token({"sub": "42"})
    assert isinstance(token, str)
    assert len(token) > 10


@pytest.mark.asyncio
async def test_get_current_user_id_valid():
    """Проверяем корректную работу зависимости get_current_user_id"""
    token = create_access_token({"sub": "7"})
    user_id = await get_current_user_id(token)
    assert user_id == 7


@pytest.mark.asyncio
async def test_get_current_user_id_invalid_token():
    """
    Проверяем что корректно выбрасывается ошибка
    если передать не корректный токен
    """
    with pytest.raises(HTTPException) as exc:
        await get_current_user_id("wrong_token")
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_get_current_user_id_missing_sub():
    """
    Проверка, что в токене есть payload с ключем sub
    """
    token = create_access_token({"data": "no sub field"})
    with pytest.raises(HTTPException) as exc:
        await get_current_user_id(token)
    assert exc.value.status_code == 401
