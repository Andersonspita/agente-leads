from django.conf import settings
from rest_framework.permissions import SAFE_METHODS, BasePermission


def is_verified(request):
    user = request.user
    if not (user and user.is_authenticated and user.is_active):
        return False
    if not settings.REQUIRE_2FA:
        return True
    return user_is_verified(user)


def user_is_verified(user) -> bool:
    # O OTPMiddleware (e o otp_login) preenchem `otp_device` quando o 2FA foi confirmado nesta sessão.
    return getattr(user, "otp_device", None) is not None


class IsVerifiedUser(BasePermission):
    """Usuário autenticado e com 2FA confirmado nesta sessão."""

    message = "Autenticação em dois fatores obrigatória."

    def has_permission(self, request, view):
        return is_verified(request)


class IsAdminOrReadOnly(BasePermission):
    def has_permission(self, request, view):
        if not is_verified(request):
            return False
        return request.method in SAFE_METHODS or request.user.is_admin


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return is_verified(request) and request.user.is_admin
