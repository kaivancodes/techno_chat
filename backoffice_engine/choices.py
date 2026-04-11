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

class AdminTeamChoices(models.TextChoices):
    CORE = "Core", "Core"
    HR = "HR", "HR"

class ContributorTeamChoices(models.TextChoices):
    CORE = "Core", "Core"
    HR = "HR", "HR"
    PHP = "PHP", "PHP"
    MERN_STACK = "MERN Stack", "MERN Stack"
    ANDROID = "Android", "Android"
    IOS = "IOS", "IOS"
    FLUTTER = "Flutter", "Flutter"
    PYTHON = "Python", "Python"
    AI_ML = "AI/ML", "AI/ML"
    DEVOPS = "DevOps", "DevOps"
    BA = "BA", "BA"
    BDE = "BDE", "BDE"
    NETWORK = "Network", "Network"
    QA = "QA", "QA"