"""What can go wrong talking to the model, and what we tell OUR caller about it.

Provider details (status codes, messages, keys) go to the server log only. Callers get a clear, safe message.
"""


class LLMError(Exception):
    http_status = 502
    outcome = "provider_error"           # recorded in the cost log
    public_message = "The language model service failed. Please try again."

    def __init__(self, detail: str = "", *, attempts: int = 1, retry_after: float | None = None):
        super().__init__(detail or self.public_message)
        self.attempts = attempts
        self.retry_after = retry_after

    @property
    def headers(self) -> dict | None:
        if self.retry_after:
            return {"Retry-After": str(int(self.retry_after) + (self.retry_after % 1 > 0))}
        return None


class LLMTimeout(LLMError):
    http_status = 504
    outcome = "timeout"
    public_message = "The language model did not answer in time. Please try again."


class LLMRateLimited(LLMError):
    http_status = 503
    outcome = "rate_limited"
    public_message = "The language model is rate-limited right now. Please try again shortly."


class LLMUnavailable(LLMError):
    http_status = 502
    outcome = "provider_error"
    public_message = "The language model service is unavailable. Please try again."


class LLMAuthError(LLMError):
    http_status = 502
    outcome = "auth_error"
    public_message = "The language model rejected this server's credentials (server configuration problem)."


class LLMRejected(LLMError):
    http_status = 502
    outcome = "rejected"
    public_message = "The language model provider rejected the request (server configuration problem)."
