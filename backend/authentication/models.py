from django.db import models
from django.contrib.auth.models import AbstractBaseUser, PermissionsMixin, BaseUserManager
from django.utils import timezone


class UserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email field must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(email, password, **extra_fields)


class User(AbstractBaseUser, PermissionsMixin):
    email = models.EmailField(unique=True, db_index=True)
    name = models.CharField(max_length=255, blank=True, default='')
    avatar_url = models.URLField(max_length=1024, blank=True, default='')
    
    # OAuth Identifiers
    telegram_id = models.BigIntegerField(null=True, blank=True, unique=True, db_index=True)
    google_sub = models.CharField(max_length=255, null=True, blank=True, unique=True, db_index=True)
    
    # Storage accounting
    storage_used = models.BigIntegerField(default=0, help_text="Total bytes confirmed stored")
    storage_reserved = models.BigIntegerField(default=0, help_text="Bytes currently reserved by ongoing uploads")
    storage_quota = models.BigIntegerField(null=True, blank=True, default=None, help_text="Null means unlimited Telegram storage")
    
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)
    date_joined = models.DateTimeField(default=timezone.now)

    objects = UserManager()

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.email

    @property
    def available_quota(self) -> int:
        if self.storage_quota is None:
            return 10**18  # Unlimited Telegram Storage (~1 Exabyte)
        return max(0, self.storage_quota - (self.storage_used + self.storage_reserved))
