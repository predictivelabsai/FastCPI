from api.account_deletion import delete_user_data


class _Result:
    def __init__(self, row=None):
        self._row = row

    def fetchone(self):
        return self._row


class _FakeDb:
    def __init__(self, user_exists=True):
        self.user_exists = user_exists
        self.statements = []
        self.committed = False

    def execute(self, statement, params):
        self.statements.append((str(statement), params))
        if len(self.statements) == 1:
            return _Result((42,) if self.user_exists else None)
        return _Result()

    def commit(self):
        self.committed = True


def test_delete_user_data_removes_all_user_owned_records():
    db = _FakeDb()

    assert delete_user_data(db, 42) is True

    sql = "\n".join(statement for statement, _ in db.statements)
    for table in (
        "chat_messages",
        "chat_sessions",
        "favorites",
        "saved_searches",
        "garage_cars",
        "user_profiles",
        "chat_users",
    ):
        assert f"carhero.{table}" in sql
    assert all(params == {"uid": 42} for _, params in db.statements)
    assert db.committed is True


def test_delete_user_data_returns_false_for_missing_user():
    db = _FakeDb(user_exists=False)

    assert delete_user_data(db, 999) is False

    assert len(db.statements) == 1
    assert db.committed is False
