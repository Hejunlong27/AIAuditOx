"""数据库连接与初始化（PART 16）。

选型说明：
- MVP 用 SQLite 单文件，路径由配置注入，**不放在 skills/ 下**；
- 开启 ``foreign_keys`` 与 WAL：外键约束缺失会让"证据挂在不存在任务上"
  这种脏数据静默通过；
- PostgreSQL 预留：只要 ``DATABASE_URL`` 换成 ``postgresql+psycopg://``，
  本模块的会话管理无需改动（ORM 层不使用 SQLite 方言特性）。
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import Engine, create_engine, event
from sqlalchemy.orm import Session, sessionmaker

from agent.storage.orm import Base


class Database:
    """数据库门面：建引擎、建表、给 Session。"""

    def __init__(self, url: str, *, echo: bool = False) -> None:
        self.url = url
        is_sqlite = url.startswith("sqlite")
        connect_args = {"check_same_thread": False} if is_sqlite else {}
        if is_sqlite:
            self._ensure_sqlite_dir(url)
        self.engine: Engine = create_engine(
            url,
            echo=echo,
            future=True,
            connect_args=connect_args,
            pool_pre_ping=True,
        )
        if is_sqlite:
            self._install_sqlite_pragmas(self.engine)
        self._session_factory = sessionmaker(
            bind=self.engine, expire_on_commit=False, class_=Session
        )

    @staticmethod
    def _ensure_sqlite_dir(url: str) -> None:
        # sqlite:///relative/path.db 或 sqlite:////abs/path.db
        raw = url.split("sqlite:///", 1)[-1]
        if raw in ("", ":memory:"):
            return
        path = Path(raw)
        path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def _install_sqlite_pragmas(engine: Engine) -> None:
        @event.listens_for(engine, "connect")
        def _set_pragmas(dbapi_conn, _record) -> None:  # noqa: ANN001
            cursor = dbapi_conn.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.execute("PRAGMA busy_timeout=5000")
            cursor.close()

    def create_all(self) -> None:
        Base.metadata.create_all(self.engine)

    def drop_all(self) -> None:
        """仅测试使用。生产代码禁止调用。"""
        Base.metadata.drop_all(self.engine)

    @contextmanager
    def session(self) -> Iterator[Session]:
        """事务边界：正常提交，异常回滚。"""
        sess = self._session_factory()
        try:
            yield sess
            sess.commit()
        except Exception:
            sess.rollback()
            raise
        finally:
            sess.close()

    def dispose(self) -> None:
        self.engine.dispose()


def init_database(url: str, *, echo: bool = False) -> Database:
    """建库 + 建表，返回可用门面。"""
    db = Database(url, echo=echo)
    db.create_all()
    return db
