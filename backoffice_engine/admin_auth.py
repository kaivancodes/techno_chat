import re
from django.core.exceptions import ValidationError


def _check_email_domain(email):
    if not email.endswith('@technostacks.com'):
        raise ValidationError('Only @technostacks.com email addresses are allowed.')


def _check_password_strength(password):
    if len(password) < 8:
        raise ValidationError('Password must be at least 8 characters.')
    if not re.search(r'[A-Z]', password):
        raise ValidationError('Password must contain at least one uppercase letter.')
    if not re.search(r'[a-z]', password):
        raise ValidationError('Password must contain at least one lowercase letter.')
    if not re.search(r'\d', password):
        raise ValidationError('Password must contain at least one number.')
    if not re.search(r'[!@#$%^&*()\-_=+\[\]{}|;:\'",.<>?/`~\\]', password):
        raise ValidationError('Password must contain at least one special character.')


def create_admin(email, password):
    from backoffice_engine.models import AdminUser, AdminProfile

    # Validate input
    _check_email_domain(email)
    _check_password_strength(password)

    # Create and save AdminUser
    admin = AdminUser(email=email, is_staff=True, is_superuser=True)
    admin.set_password(password)
    admin.save()

    # Initialize empty AdminProfile
    AdminProfile.objects.create(
        admin=admin,
        is_profile_complete=False
    )
    return admin