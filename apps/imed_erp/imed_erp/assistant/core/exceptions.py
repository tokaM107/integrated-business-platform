# The assistant's own errors. The API turns them into words for the user.


class AssistantError(Exception):
	"""Base of the assistant's errors."""


class ModelUnavailable(AssistantError):
	"""The model could not be called: `reason` is "quota" (the key's limit), "overload" (the provider's demand) or
	"not_configured" (no key). Not the ERP's fault; said as such to the user."""

	def __init__(self, reason: str, detail: str = ""):
		super().__init__(detail or reason)
		self.reason = reason


class ToolConflict(AssistantError):
	"""Two integrations registered a tool under the same name: refused, so one can never replace another's read."""
