class TechnoChatError(Exception):
    user_message = "Something went wrong. Please try again."
    internal_note = "Unclassified error."

    def __init__(self, message=None, internal=None):
        super().__init__()
        if message is not None:
            self.user_message = message
        if internal is not None:
            self.internal_note = internal

class NetworkConnectionError(TechnoChatError):
    user_message = "No internet connection."
    internal_note = "Network failure."

class MultipleFilesError(TechnoChatError):
    user_message = "Please upload one file at a time."
    internal_note = "Multiple files in one request."

class InvalidFileTypeError(TechnoChatError):
    user_message = "File type not supported. Please upload a supported file type."
    internal_note = "Unsupported file extension."

class FileTooLargeError(TechnoChatError):
    internal_note = "File exceeded size limit."

    def __init__(self, max_mb, file_type_label):
        self.user_message = f"File too large. Maximum {max_mb}MB allowed for {file_type_label} files."
        super().__init__(self.user_message)

class VLMQuotaExceededError(TechnoChatError):
    user_message = "Your image processing quota reached."
    internal_note = "Gemini VLM API returned 429."

class VLMStandaloneImageError(TechnoChatError):
    user_message = "Something went wrong. Image processing failed."
    internal_note = "VLM failed on standalone image."

class VLMEmbeddedImageError(TechnoChatError):
    user_message = "A file was saved but an image inside it could not be processed."
    internal_note = "VLM failed on embedded image."

class NoTextExtractedError(TechnoChatError):
    user_message = "No readable text could be extracted from the file."
    internal_note = "extract_file_text() returned empty."

class IngestionError(TechnoChatError):
    user_message = "The file was saved but could not be processed for search. Please try re-uploading."
    internal_note = "Ingestion pipeline failed."

class ChatResponseError(TechnoChatError):
    user_message = "The response could not be generated. Please try again."
    internal_note = "build_chat_prompt() failed."

class ChatModelQuotaError(TechnoChatError):
    user_message = "Model quota reached. Select another model to continue chatting."
    internal_note = "LLM API returned 429."

class ChatMessageSendError(TechnoChatError):
    user_message = "Message sent failure. Try again."
    internal_note = "Query embedding or search failed before LLM call."

class AuthenticationError(TechnoChatError):
    user_message = "Please enter both email and password."
    internal_note = "Login submitted with missing credentials."

class ProfileValidationError(TechnoChatError):
    user_message = "Please fill in all required fields."
    internal_note = "Profile form missing required field."

class EmptySessionError(TechnoChatError):
    user_message = "The session has no documents attached. Please create a new session with files."
    internal_note = "Session has no linked files."

class WebSearchError(TechnoChatError):
    user_message  = 'Web search failed. Please try again.'
    internal_note = 'Serper.dev API call failed.'

class PageRenderError(TechnoChatError):
    user_message  = 'Page preview could not be generated.'
    internal_note = 'PDF page rendering failed.'

class ImageRetrievalError(TechnoChatError):
    user_message  = 'Could not retrieve the image from the document.'
    internal_note = 'Image extraction from document failed.'