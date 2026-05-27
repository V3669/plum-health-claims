class AgentError(Exception):
    pass


class IllegalStateTransition(Exception):
    pass


class UnknownCategoryError(AgentError):
    pass
