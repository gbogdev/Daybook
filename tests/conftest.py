import pytest

from daybook.db import Database
from daybook.service import TaskService


@pytest.fixture
def db(tmp_path):
    database = Database(tmp_path / "test.db")
    yield database
    database.close()


@pytest.fixture
def svc(db):
    return TaskService(db)


@pytest.fixture
def project(svc):
    return svc.create_project("Work")
