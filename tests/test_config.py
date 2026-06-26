from pathlib import Path

from trusttunel_bot.config import load_config


def test_load_config_reads_hev_socks5_fields(tmp_path: Path):
    config_path = tmp_path / "bot.toml"
    config_path.write_text(
        '''
credentials_file = "/tmp/credentials.toml"
hev_socks5_enabled = true
hev_socks5_auth_file = "/etc/hev-socks5-server/auth.txt"
hev_socks5_service_name = "custom-hev"
hev_socks5_public_host = "proxy.example.com"
hev_socks5_public_port = 1081
hev_socks5_scheme = "socks5"
hev_socks5_sync_on_add = false
hev_socks5_lazy_create = false
hev_socks5_mark_start = 32
''',
        encoding="utf-8",
    )
    config = load_config(config_path)
    assert config.hev_socks5_enabled is True
    assert config.hev_socks5_auth_file == Path("/etc/hev-socks5-server/auth.txt")
    assert config.hev_socks5_service_name == "custom-hev"
    assert config.hev_socks5_public_host == "proxy.example.com"
    assert config.hev_socks5_public_port == 1081
    assert config.hev_socks5_scheme == "socks5"
    assert config.hev_socks5_sync_on_add is False
    assert config.hev_socks5_lazy_create is False
    assert config.hev_socks5_mark_start == 32
