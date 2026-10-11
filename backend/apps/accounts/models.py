from django.contrib.auth.models import AbstractUser, UserManager as BaseUserManager
from django.db import models
from django.utils import timezone


class UserManager(BaseUserManager):
    def _create_user(self, email, password, **extra):
        email = self.normalize_email(email)
        extra.setdefault("username", email)
        user = self.model(email=email, **extra)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_user(self, email, password=None, **extra):
        extra.setdefault("is_staff", False)
        extra.setdefault("is_superuser", False)
        return self._create_user(email, password, **extra)

    def create_superuser(self, email, password=None, **extra):
        extra.setdefault("is_staff", True)
        extra.setdefault("is_superuser", True)
        extra.setdefault("role", User.Role.ADMIN)
        return self._create_user(email, password, **extra)


class User(AbstractUser):
    class Role(models.TextChoices):
        ADMIN = "admin", "Administrador"
        ANALYST = "analista", "Analista"

    email = models.EmailField("e-mail", unique=True)
    role = models.CharField("perfil", max_length=10, choices=Role.choices, default=Role.ANALYST)
    failed_logins = models.PositiveSmallIntegerField(default=0)
    locked_until = models.DateTimeField(null=True, blank=True)

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    objects = UserManager()

    @property
    def is_admin(self):
        return self.role == self.Role.ADMIN or self.is_superuser

    @property
    def is_locked(self):
        return bool(self.locked_until and self.locked_until > timezone.now())

    def __str__(self):
        return self.get_full_name() or self.email
