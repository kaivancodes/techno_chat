from django.utils import timezone
from django.shortcuts import redirect
from backoffice_engine.models import AdminUser, User

def get_current_datetime():
    """Return the current local datetime (timezone-aware)."""
    return timezone.localtime(timezone.now())

def rows_to_text(rows: list) -> str:
    lines = []
    for row in rows:
        if row:
            # convert None cells to empty string
            lines.append(" | ".join("" if cell is None else str(cell) for cell in row))
    return "[Table:\n" + "\n".join(lines) + "]"


def check_profile_completion(request):
    role = request.session.get('role')
    user_id = request.session.get('user_id')

    if not role or not user_id:
        return redirect('login')

    if role == 'admin':
        admin = AdminUser.objects.get(id=user_id)
        if not admin.profile_completed:
            return redirect('admin_profile')

    elif role == 'user':
        user = User.objects.get(id=user_id)
        if not user.profile_completed:
            return redirect('user_profile')

    return None  # ✅ important