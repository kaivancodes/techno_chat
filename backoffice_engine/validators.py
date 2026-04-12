"""
Validation logic for TechnoChat.
Functions here check user input and raise typed exceptions from .exceptions.
"""

import re
from django.core.exceptions import ValidationError
from backoffice_engine.choices import FileType
from backoffice_engine.constants import (
    MAX_SIZE_IMAGE, MAX_SIZE_PDF, MAX_SIZE_DOC,
    MAX_SIZE_EXCEL, MAX_SIZE_TXT, MAX_SIZE_CSV, MAX_SIZE_MD,
    VALID_CHAT_MODES, VALID_SESSION_TYPES,
)
from backoffice_engine.exceptions import (
    MultipleFilesError,
    InvalidFileTypeError,
    FileTooLargeError,
    AuthenticationError,
    ProfileValidationError,
    ChatResponseError,
    EmptySessionError,
)
from backoffice_engine.models import UserProfile

def validate_uploaded_files_length(files):
    if len(files) != 1:
        raise MultipleFilesError()

def validate_uploaded_file_type(file_type):
    if not file_type:
        raise InvalidFileTypeError()

def validate_file_size(file, file_type):
    _SIZE_LIMITS = {
        FileType.IMAGE: MAX_SIZE_IMAGE,
        FileType.PDF:   MAX_SIZE_PDF,
        FileType.DOC:   MAX_SIZE_DOC,
        FileType.EXCEL: MAX_SIZE_EXCEL,
        FileType.TXT:   MAX_SIZE_TXT,
        FileType.CSV:   MAX_SIZE_CSV,
        FileType.MD:    MAX_SIZE_MD,
    }
    max_mb = _SIZE_LIMITS.get(file_type)
    if max_mb is None:
        return

    max_bytes = max_mb * 1024 * 1024
    if file.size > max_bytes:
        raise FileTooLargeError(max_mb, file_type.label)

def validate_login_credentials(email, password):
    if not email or not password:
        raise AuthenticationError("Please enter both email and password.")

def validate_profile_fields(first_name, surname, username):
    if not first_name:
        raise ProfileValidationError("First name is required.")
    if not surname:
        raise ProfileValidationError("Surname is required.")
    if not username:
        raise ProfileValidationError("Username is required.")

def validate_profile_username(username: str, current_profile_pk: int):
    """
    Validates a username for the given profile.
    Checks regex and uniqueness.
    Raises ValidationError if invalid.
    """
    username_pattern = re.compile(r'^[a-z][a-z0-9._]{0,29}$')

    if re.search(r"\s", username or ""):
        raise ValidationError("Spaces not allowed in username.")

    if not username_pattern.match(username):
        raise ValidationError("Username must start with a letter and contain only letters, numbers, underscores, or dots (max 30 chars).")

    if UserProfile.objects.filter(username__iexact=username).exclude(pk=current_profile_pk).exists():
        raise ValidationError("This username is already taken.")

def validate_chat_query(query):
    if not query:
        raise ChatResponseError("Please enter a message before sending.")

def validate_session_has_files(file_ids):
    if not file_ids:
        raise EmptySessionError()

def validate_chat_mode(chat_mode: str):
    if chat_mode not in VALID_CHAT_MODES:
        raise ChatResponseError(
            f'Invalid chat mode: {chat_mode}. Valid: {VALID_CHAT_MODES}'
        )

def validate_session_type(session_type: str):
    if session_type not in VALID_SESSION_TYPES:
        raise ProfileValidationError(
            f'Invalid session type: {session_type}.'
        )
