from unittest.mock import patch


def test_import_main_does_not_create_engine() -> None:
    with patch("app.db.session.create_engine") as create_engine:
        import app.main  # noqa: F401

    create_engine.assert_not_called()


def test_import_session_module_does_not_create_engine() -> None:
    with patch("app.db.session.create_engine") as create_engine:
        import importlib

        import app.db.session as session_module

        importlib.reload(session_module)

    create_engine.assert_not_called()


def test_get_session_factory_is_lazy() -> None:
    from app.db.session import _build_engine, _build_session_factory, get_session_factory

    _build_engine.cache_clear()
    _build_session_factory.cache_clear()

    with patch("app.db.session.create_engine") as create_engine:
        factory = get_session_factory()

    create_engine.assert_called_once()
    assert factory is not None

    _build_engine.cache_clear()
    _build_session_factory.cache_clear()
