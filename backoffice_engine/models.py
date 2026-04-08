from django.db import models
from backoffice_engine.choices import FileType, FileProcessingStatus, SessionType
from django.core.validators import RegexValidator
from django.utils.timezone import now


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
        validators=[
            RegexValidator(
                regex=r'^[^@]+@technostacks\.com$',
                message='Only @technostacks.com email addresses are allowed.'
            )
        ]
    )
    password = models.CharField(max_length=255)

    def __str__(self):
        return f"{self.id} - {self.email}"


class UserProfile(BaseModel):
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile'
    )
    first_name = models.CharField(max_length=100, blank=True, default="")
    surname = models.CharField(max_length=100, blank=True, default="")

    username_validator = RegexValidator(
        regex=r'^[a-zA-Z][a-zA-Z0-9._]{0,29}$',
        message=(
            'Username must start with a letter, be max 30 characters, '
            'and contain only letters, numbers, underscores, or dots.'
        )
    )
    username = models.CharField(
        max_length=30,
        unique=True,
        blank=True,
        null=True,
        validators=[username_validator]
    )
    position_at_technostacks = models.CharField(max_length=150, blank=True, default="")
    team = models.CharField(max_length=100, blank=True, default="")
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