import os, sys
os.environ["ENVIRONMENT"] = "development"
os.environ.setdefault("MONGODB_URI", "mongodb://localhost:27017")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379")
os.environ.setdefault("RAZORPAY_KEY_ID", "rzp_test")
os.environ.setdefault("RAZORPAY_KEY_SECRET", "secret")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from unittest.mock import AsyncMock, patch

from src.services.customer_auth_service import CustomerAuthService
from src.security.exceptions import AccountLockedError


@pytest.mark.asyncio
async def test_repeated_failed_otp_locks_the_identifier():
    with patch("src.services.customer_auth_service.LoginLockoutService") as mock_lockout_cls, \
         patch("src.services.customer_auth_service.CustomerSessionService"), \
         patch("src.services.customer_auth_service.UserService"):
        lockout_instance = mock_lockout_cls.return_value
        lockout_instance.assert_not_locked = AsyncMock()
        lockout_instance.record_failure = AsyncMock()
        service = CustomerAuthService()
        with patch.object(service, "_channel") as mock_channel_factory:
            mock_channel_factory.return_value.verify_otp = AsyncMock(return_value=False)
            result = await service.verify_otp_and_login("buyer@example.com", "000000", ip="1.2.3.4")

        assert result is None
        lockout_instance.record_failure.assert_awaited_once_with("1.2.3.4", "buyer@example.com")


@pytest.mark.asyncio
async def test_locked_identifier_raises_before_checking_the_otp():
    with patch("src.services.customer_auth_service.LoginLockoutService") as mock_lockout_cls, \
         patch("src.services.customer_auth_service.CustomerSessionService"), \
         patch("src.services.customer_auth_service.UserService"):
        lockout_instance = mock_lockout_cls.return_value
        lockout_instance.assert_not_locked = AsyncMock(side_effect=AccountLockedError(300))
        service = CustomerAuthService()
        with patch.object(service, "_channel") as mock_channel_factory:
            mock_channel_factory.return_value.verify_otp = AsyncMock()
            with pytest.raises(AccountLockedError):
                await service.verify_otp_and_login("buyer@example.com", "000000", ip="1.2.3.4")
            mock_channel_factory.return_value.verify_otp.assert_not_called()
