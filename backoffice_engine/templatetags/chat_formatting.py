import re

from django import template
from django.utils.html import escape
from django.utils.safestring import mark_safe


register = template.Library()

_BULLET_PATTERN = re.compile(r"^[-*]\s+(.+)")
_NUMBERED_PATTERN = re.compile(r"^\d+\.\s+(.+)")
_URL_PATTERN = re.compile(r"(https?://[^\s<>()]+)", re.IGNORECASE)
_BOLD_PATTERN = re.compile(r"\*\*(.*?)\*\*")
_CODE_PATTERN = re.compile(r"`(.*?)`")


def _linkify(text: str) -> str:
    def replacer(match):
        url = match.group(1).rstrip(").,;:!?]}>\"'")
        return f'<a href="{url}" target="_blank" rel="noopener noreferrer" class="inline-msg-link">{url}</a>'

    return _URL_PATTERN.sub(replacer, text)


def _inline_format(text: str) -> str:
    formatted = escape(text or "")
    formatted = _BOLD_PATTERN.sub(r"<strong>\1</strong>", formatted)
    formatted = _CODE_PATTERN.sub(r'<code class="msg-code">\1</code>', formatted)
    return _linkify(formatted)


@register.filter
def render_chat_message(text):
    lines = str(text or "").splitlines()
    html = []
    list_type = None

    def close_list():
        nonlocal list_type
        if list_type:
            html.append(f"</{list_type}>")
            list_type = None

    for line in lines:
        trimmed = line.strip()
        bullet_match = _BULLET_PATTERN.match(trimmed)
        numbered_match = _NUMBERED_PATTERN.match(trimmed)

        if not trimmed:
            close_list()
            html.append("<br>")
            continue

        if bullet_match:
            if list_type != "ul":
                close_list()
                list_type = "ul"
                html.append('<ul class="msg-list">')
            html.append(f"<li>{_inline_format(bullet_match.group(1))}</li>")
            continue

        if numbered_match:
            if list_type != "ol":
                close_list()
                list_type = "ol"
                html.append('<ol class="msg-list">')
            html.append(f"<li>{_inline_format(numbered_match.group(1))}</li>")
            continue

        close_list()
        html.append(f"<p>{_inline_format(trimmed)}</p>")

    close_list()
    return mark_safe("".join(html) or "<p></p>")
