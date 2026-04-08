from django.utils import timezone

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
