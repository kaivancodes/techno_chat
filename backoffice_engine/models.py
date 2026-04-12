from django.db import models
from backoffice_engine.choices import FileType, FileProcessingStatus, SessionType, AdminTeamChoices, ContributorTeamChoices
from django.core.validators import RegexValidator
from django.core.exceptions import ValidationError
from django.utils.timezone import now
from django.contrib.auth.models import AbstractUser
from django.contrib.auth.hashers import make_password, check_password

# ✅ EMAIL FUNCTION
def check_email_domain(value):
    validator = RegexValidator(
        regex=r'^[^@]+@technostacks\.com$',
        message='Only @technostacks.com email addresses are allowed.'
    )
    validator(value)


# ✅ PASSWORD FUNCTION
def check_password_strength(value):
    validator = RegexValidator(
        regex=r'^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)(?=.*[!@#$%^&*(),.?":{}|<>]).{8,}$',
        message=(
            "Password must be at least 8 characters and include "
            "uppercase, lowercase, number, and special character."
        )
    )
    validator(value)


# ✅ USERNAME FUNCTION
def check_username(value):
    if any(char.isspace() for char in (value or "")):
        raise ValidationError("Spaces not allowed in username.")
    validator = RegexValidator(
        regex=r'^[a-zA-Z][a-zA-Z0-9._]{0,29}$',
        message=(
            "Username must start with a letter, be max 30 characters, "
            "and contain only letters, numbers, underscores, or dots."
        )
    )
    validator(value)


class AdminUser(AbstractUser):
    """
    Separate admin user model using Django's AbstractUser.
    Registered via createsuperuser or admin register page.
    Email must end in @technostacks.com.
    Username field is email.
    """

    username = None

    email = models.EmailField(
        max_length=255,
        unique=True,
        validators=[check_email_domain]
    )

    password = models.CharField(
        max_length=255,
        validators=[check_password_strength]
    )

    profile_completed = models.BooleanField(default=False)
    # Override username to use email
    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = []  # removes username from createsuperuser prompt

    # Remove username field requirement


    class Meta:
        verbose_name = 'Admin User'
        verbose_name_plural = 'Admin Users'

    def __str__(self):
        return self.email

class BaseModel(models.Model):
    id = models.BigAutoField(primary_key=True)

    created_at = models.DateTimeField(default=now)   # ✅ ONLY default
    updated_at = models.DateTimeField(default=now)   # ✅ ONLY default

    class Meta:
        abstract = True
        ordering = ["-id"]

    def save(self, *args, **kwargs):
        self.updated_at = now()  # ✅ Django handles update
        super().save(*args, **kwargs)

class User(BaseModel):
    email = models.EmailField(
        max_length=255,
        unique=True,
        validators=[check_email_domain]
    )
    password = models.CharField(
        max_length=255,
        validators=[check_password_strength]
    )
    profile_completed = models.BooleanField(default=False)

    def __str__(self):
        return f"{self.id} - {self.email}"


class AdminProfile(BaseModel):
    admin = models.OneToOneField(
        AdminUser,
        on_delete=models.CASCADE,
        related_name='admin_profile'
    )
    first_name = models.CharField(max_length=100, blank=True, default="")
    surname = models.CharField(max_length=100, blank=True, default="")
    username = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
        validators=[check_username],
    )
    position_at_technostacks = models.CharField(max_length=150, blank=True, default="")
    team = models.CharField(
        max_length=100,
        blank=True,
        default="",
        choices=AdminTeamChoices.choices
    )
    is_profile_complete = models.BooleanField(default=False)

    def get_initials(self):
        first = self.first_name[0].upper() if self.first_name else ""
        last = self.surname[0].upper() if self.surname else ""
        if first and last:
            return f"{first}{last}"
        return first or last or self.admin.email[0].upper()

    def get_display_name(self):
        if self.first_name and self.surname:
            return f"{self.first_name} {self.surname}"
        return self.admin.email.split("@")[0]
    def __str__(self):
        return f"Profile of {self.admin.email}"

class UserProfile(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    first_name = models.CharField(max_length=100, blank=True, default="")
    surname = models.CharField(max_length=100, blank=True, default="")


    username = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
        validators=[check_username]
    )
    position_at_technostacks = models.CharField(max_length=150, blank=True, default="")
    team = models.CharField(
        max_length=100,
        blank=True,
        default="",
        choices=ContributorTeamChoices.choices
    )
    is_profile_complete = models.BooleanField(default=False)

    def get_initials(self):
        first = self.first_name[0].upper() if self.first_name else ""
        last = self.surname[0].upper() if self.surname else ""
        if first and last:
            return f"{first}{last}"
        return (first or last or self.user.email[0].upper())

    def get_display_name(self):
        if self.first_name and self.surname:
            return f"{self.first_name} {self.surname}"
        return self.user.email.split("@")[0]

    def __str__(self):
        return f"Profile of {self.user.email}"

class File(BaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='files'
    )

    file_type = models.CharField(
        max_length=50,
        choices=FileType,
        blank=True,
        null=True
    )

    file = models.FileField(
        upload_to='files/'
    )

    original_filename = models.CharField(
        max_length=512,
        blank=True,
        default=""
    )

    embedding_status = models.CharField(
        max_length=50,
        choices=FileProcessingStatus,
        default=FileProcessingStatus.PENDING
    )

    def __str__(self):
        return f"{self.id} - {self.original_filename or self.file.name}"


class ChatSession(BaseModel):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_sessions'
    )

    files = models.ManyToManyField(
        File,
        related_name='chat_sessions',
        blank=True
    )

    title = models.CharField(
        max_length=255,
        default="New Chat"
    )

    session_type = models.CharField(
        max_length=20,
        choices=SessionType.choices,
        default=SessionType.CHAT_WITH_FILE,
    )

    def __str__(self):
        return f"{self.id} - {self.title}"


class ChatMessage(BaseModel):
    session = models.ForeignKey(
        ChatSession,
        on_delete=models.CASCADE,
        related_name='messages'
    )

    question = models.TextField()
    answer = models.TextField()

    model_used = models.CharField(
        max_length=100,
        blank=True,
        default=""
    )
    sources = models.JSONField(default=list, blank=True)

    chat_mode = models.CharField(
        max_length=20,
        default='rag',
        blank=True,
    )

    def __str__(self):
        return f"{self.id} - {self.question[:50]}"
