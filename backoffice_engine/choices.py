from django.db import models

class FileProcessingStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    COMPLETED = "completed", "Completed"
    FAILED = "failed", "Failed"

class FileType(models.TextChoices):
    IMAGE = "image", "Image"
    PDF = "pdf", "PDF"
    DOC = "doc", "Document"
    EXCEL = "excel", "Excel Sheet"
    POWER = "power", "PowerPoint"
    TXT = "txt", "Text File"
    CSV = "csv", "CSV File"
    MD = "md", "Markdown File"

class SessionType(models.TextChoices):
    CHAT_WITH_FILE = 'chat_with_file', 'Chat with File'
    GENERAL_CHAT   = 'general_chat',   'General Chat'