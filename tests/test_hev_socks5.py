from pathlib import Path

from trusttunel_bot.config import BotConfig
from trusttunel_bot.hev_socks5 import (
    HevSocks5User,
    create_hev_socks5_user,
    delete_hev_socks5_user,
    ensure_hev_socks5_user,
    format_hev_socks5_access,
    load_hev_auth_file,
    save_hev_auth_file,
)


def _config(tmp_path: Path) -> BotConfig:
    return BotConfig(
        credentials_file=tmp_path / "credentials.toml",
        hev_socks5_enabled=True,
        hev_socks5_auth_file=tmp_path / "auth.txt",
        hev_socks5_public_host="proxy.example.com",
        hev_socks5_public_port=1080,
        hev_socks5_mark_start=0x10,
    )


def test_load_empty_auth_file(tmp_path):
    path = tmp_path / "auth.txt"
    path.write_text("\n", encoding="utf-8")
    assert load_hev_auth_file(path) == []
    assert load_hev_auth_file(tmp_path / "missing.txt") == []


def test_parse_and_save_auth_file(tmp_path):
    path = tmp_path / "auth.txt"
    users = [HevSocks5User("alice", "pass1", "10"), HevSocks5User("bob", "pass2", "11")]
    save_hev_auth_file(path, users)
    assert path.read_text(encoding="utf-8") == "alice pass1 10\nbob pass2 11\n"
    assert load_hev_auth_file(path) == users
    assert oct(path.stat().st_mode & 0o777) == "0o600"


def test_duplicate_username_rejected(tmp_path):
    path = tmp_path / "auth.txt"
    path.write_text("alice pass1 10\nalice pass2 11\n", encoding="utf-8")
    try:
        load_hev_auth_file(path)
    except ValueError as exc:
        assert "Duplicate" in str(exc)
    else:
        raise AssertionError("duplicate username must fail")


def test_create_generates_unique_marks_and_existing_user_is_not_changed(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr("trusttunel_bot.hev_socks5.reload_hev_socks5", lambda config: type("R", (), {"ok": True})())
    alice = create_hev_socks5_user(config, "alice", password="old-pass")
    bob = create_hev_socks5_user(config, "bob", password="bob-pass")
    alice_again = create_hev_socks5_user(config, "alice", password="new-pass")
    assert alice.mark == "10"
    assert bob.mark == "11"
    assert alice_again.password == "old-pass"
    assert load_hev_auth_file(config.hev_socks5_auth_file) == [alice, bob]


def test_ensure_does_not_rotate_existing_password(tmp_path, monkeypatch):
    config = _config(tmp_path)
    monkeypatch.setattr("trusttunel_bot.hev_socks5.reload_hev_socks5", lambda config: type("R", (), {"ok": True})())
    create_hev_socks5_user(config, "alice", password="stable")
    assert ensure_hev_socks5_user(config, "alice").password == "stable"


def test_delete_removes_only_requested_user(tmp_path):
    config = _config(tmp_path)
    save_hev_auth_file(
        config.hev_socks5_auth_file,
        [HevSocks5User("alice", "pass1", "10"), HevSocks5User("bob", "pass2", "11")],
    )
    assert delete_hev_socks5_user(config, "alice") is True
    assert load_hev_auth_file(config.hev_socks5_auth_file) == [HevSocks5User("bob", "pass2", "11")]
    assert delete_hev_socks5_user(config, "missing") is False


def test_format_url_encodes_credentials(tmp_path):
    config = _config(tmp_path)
    user = HevSocks5User("name+space", "p@ss word/", "10")
    text = format_hev_socks5_access(config, user)
    assert "Password: p@ss word/" in text
    assert "socks5h://name%2Bspace:p%40ss%20word%2F@proxy.example.com:1080" in text
