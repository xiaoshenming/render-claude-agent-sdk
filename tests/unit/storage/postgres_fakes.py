from __future__ import annotations


class Cursor:
    def __init__(self, rows=(), *, rowcount: int = 1) -> None:
        self._rows = list(rows)
        self.rowcount = rowcount

    def fetchone(self):
        return None if not self._rows else self._rows.pop(0)

    def fetchall(self):
        rows, self._rows = self._rows, []
        return rows


class Transaction:
    def __init__(self, connection) -> None:
        self.connection = connection

    def __enter__(self):
        self.connection.events.append("BEGIN")
        return self

    def __exit__(self, error_type, error, traceback):
        self.connection.events.append("ROLLBACK" if error_type else "COMMIT")
        return False


class Connection:
    def __init__(self, responder=None) -> None:
        self.responder = responder or (lambda sql, parameters: Cursor())
        self.executed: list[tuple[str, object]] = []
        self.events: list[str] = []
        self.closed = False

    def transaction(self):
        return Transaction(self)

    def execute(self, sql: str, parameters=()):
        normalized = " ".join(sql.split())
        self.executed.append((normalized, parameters))
        response = self.responder(normalized, parameters)
        if isinstance(response, BaseException):
            raise response
        return response

    def close(self):
        self.closed = True
