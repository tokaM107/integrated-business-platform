# The assistant's own errors. Anything else that a tool or a model raises is wrapped here before it reaches the
# user, so the API has one place to turn them into words.


class AssistantError(Exception):
	"""Base of the assistant's errors."""


class ModelUnavailable(AssistantError):
	"""The model could not be called: the key's quota is used up (`reason = "quota"`) or the service is overloaded
	(`reason = "overload"`). Not the ERP's fault; said as such to the user."""

	def __init__(self, reason: str, detail: str = ""):
		super().__init__(detail or reason)
		self.reason = reason


class ToolNotFound(AssistantError):
	"""The model asked for a tool the registry does not hold."""


class NotAllowed(AssistantError):
	"""A read the asking user may not make (a Frappe PermissionError, named)."""
