"""Store-neutral user modification failures."""


class ModificationConflict(RuntimeError):
    pass


class ModificationNotFound(KeyError):
    pass


class ModificationStale(RuntimeError):
    pass
