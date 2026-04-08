import socket
# DOCX XML namespace
DOCX_NAMESPACE = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"

# EXTRACTION SEGMENT SIZES
TXT_SEGMENT_LINES = 40
CSV_SEGMENT_ROWS = 25
XLSX_SEGMENT_ROWS = 25

_LOCATION_FIELDS = (
    "page_index", "slide_index", "sheet_name",
    "row_start",  "row_end",
    "line_start", "line_end",
    "section_name",
)

GREETINGS = {"hi", "hello", "hey", "good morning", "good evening"}

SUMMARY = {"what is this file", "what is this document", "summarise", "summarize", "summary", "what is this about", "overview", "brief"}

CHAT_HISTORY_COUNT = 5

MAX_SIZE_IMAGE = 5
MAX_SIZE_PDF = 10
MAX_SIZE_DOC = 10
MAX_SIZE_EXCEL = 5
MAX_SIZE_TXT = 5
MAX_SIZE_CSV = 5
MAX_SIZE_MD = 5

MAX_RETRY_ATTEMPTS = 3
RETRY_BACKOFF_BASE = 1.0

NETWORK_SIGNALS = (
    "connection", "timeout", "network", "socket",
    "name or service not known", "failed to establish",
    "connection refused", "no route to host",
    "temporary failure in name resolution", "name resolution",
    "getaddrinfo", "nodename nor servname", "unreachable",
    "broken pipe", "eof occurred", "remote end closed",
    "read timed out", "ssl", "certificate",
)

NETWORK_EXCEPTION_TYPES = (
    ConnectionError, ConnectionRefusedError, ConnectionResetError,
    ConnectionAbortedError, TimeoutError, OSError,
    socket.gaierror, socket.timeout,
)

QUOTA_SIGNALS = (
    "429", "quota", "rate limit", "rate_limit",
    "too many requests", "resource_exhausted", "exceeded", "ratelimiterror",
)

# Chat mode identifiers — used in views.py routing and chat.js
CHAT_MODE_RAG        = 'rag'
CHAT_MODE_AI_ASSISTANT     = 'ai_assistant'
CHAT_MODE_WEB_SEARCH = 'web_search'
CHAT_MODE_IMAGE_GENERATION = 'image_generation'
VALID_CHAT_MODES     = (CHAT_MODE_RAG, CHAT_MODE_AI_ASSISTANT, CHAT_MODE_WEB_SEARCH, CHAT_MODE_IMAGE_GENERATION)

# Session type identifiers
SESSION_TYPE_FILE    = 'chat_with_file'
SESSION_TYPE_GENERAL = 'general_chat'
VALID_SESSION_TYPES  = (SESSION_TYPE_FILE, SESSION_TYPE_GENERAL)

# Page viewer / image extraction
PAGE_RENDER_SUPPORTED_TYPES   = ('pdf',)
PAGE_RENDER_HIGHLIGHT_MAX_LEN = 100
SOURCE_VIEWER_SUPPORTED_TYPES = ('pdf', 'doc', 'docx', 'ppt', 'pptx', 'excel', 'xlsx', 'xls', 'csv', 'txt', 'md', 'image', 'png', 'jpg', 'jpeg', 'webp', 'svg')

# Web search
WEB_SEARCH_CONTENT_SNIPPET_LEN = 600   # chars per result for LLM synthesis
DEFAULT_RAG_CHUNK_LIMIT = 8
SUMMARY_RAG_CHUNK_LIMIT = 18
DEFAULT_RAG_TOKEN_BUDGET = 2800
SUMMARY_RAG_TOKEN_BUDGET = 9000
