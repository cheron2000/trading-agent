"""
Unit tests for the new load_telegram_keys and load_alpaca_keys functions.
Requirements: 7.4, 7.5, 7.6, 5.1
"""
import pytest
from pathlib import Path
from load_keys import load_telegram_keys, load_alpaca_keys


# ── helpers ──────────────────────────────────────────────────────────────────

def write_env(tmp_path: Path, content: str) -> Path:
    p = tmp_path / "keys.env"
    p.write_text(content, encoding="utf-8")
    return p


# ── load_telegram_keys ────────────────────────────────────────────────────────

class TestLoadTelegramKeys:
    def test_returns_token_and_chat_id(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_BOT_TOKEN=123:ABC\nTELEGRAM_CHAT_ID=9876\n")
        token, chat_id = load_telegram_keys(env)
        assert token == "123:ABC"
        assert chat_id == "9876"

    def test_strips_whitespace_around_values(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_BOT_TOKEN=  tok123  \nTELEGRAM_CHAT_ID=  777  \n")
        token, chat_id = load_telegram_keys(env)
        assert token == "tok123"
        assert chat_id == "777"

    def test_ignores_comment_lines(self, tmp_path):
        content = (
            "# This is a comment\n"
            "TELEGRAM_BOT_TOKEN=mytoken\n"
            "# another comment\n"
            "TELEGRAM_CHAT_ID=42\n"
        )
        env = write_env(tmp_path, content)
        token, chat_id = load_telegram_keys(env)
        assert token == "mytoken"
        assert chat_id == "42"

    def test_case_insensitive_keys(self, tmp_path):
        env = write_env(tmp_path, "telegram_bot_token=lowertoken\ntelegram_chat_id=lowerchat\n")
        token, chat_id = load_telegram_keys(env)
        assert token == "lowertoken"
        assert chat_id == "lowerchat"

    def test_raises_file_not_found_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.env"
        with pytest.raises(FileNotFoundError):
            load_telegram_keys(missing)

    def test_raises_value_error_when_bot_token_missing(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_CHAT_ID=9876\n")
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            load_telegram_keys(env)

    def test_raises_value_error_when_chat_id_missing(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_BOT_TOKEN=mytoken\n")
        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            load_telegram_keys(env)

    def test_raises_value_error_when_both_missing(self, tmp_path):
        env = write_env(tmp_path, "AV_KEYS=some_key\n")
        with pytest.raises(ValueError):
            load_telegram_keys(env)

    def test_raises_value_error_when_bot_token_empty(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=9876\n")
        with pytest.raises(ValueError, match="TELEGRAM_BOT_TOKEN"):
            load_telegram_keys(env)

    def test_raises_value_error_when_chat_id_empty(self, tmp_path):
        env = write_env(tmp_path, "TELEGRAM_BOT_TOKEN=mytoken\nTELEGRAM_CHAT_ID=\n")
        with pytest.raises(ValueError, match="TELEGRAM_CHAT_ID"):
            load_telegram_keys(env)

    def test_other_keys_in_file_do_not_interfere(self, tmp_path):
        content = (
            "AV_KEYS=KEY1,KEY2\n"
            "GROQ_API_KEY=gsk_abc\n"
            "TELEGRAM_BOT_TOKEN=realtoken\n"
            "ALPACA_API_KEY=PK123\n"
            "TELEGRAM_CHAT_ID=55555\n"
            "ALPACA_SECRET_KEY=secret\n"
        )
        env = write_env(tmp_path, content)
        token, chat_id = load_telegram_keys(env)
        assert token == "realtoken"
        assert chat_id == "55555"


# ── load_alpaca_keys ──────────────────────────────────────────────────────────

class TestLoadAlpacaKeys:
    def test_returns_api_key_and_secret_key(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_API_KEY=PKTEST123\nALPACA_SECRET_KEY=mysecret\n")
        api_key, secret_key = load_alpaca_keys(env)
        assert api_key == "PKTEST123"
        assert secret_key == "mysecret"

    def test_strips_whitespace_around_values(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_API_KEY=  PK_abc  \nALPACA_SECRET_KEY=  sec_xyz  \n")
        api_key, secret_key = load_alpaca_keys(env)
        assert api_key == "PK_abc"
        assert secret_key == "sec_xyz"

    def test_ignores_comment_lines(self, tmp_path):
        content = (
            "# Alpaca keys below\n"
            "ALPACA_API_KEY=PKCOMMENT\n"
            "# more comments\n"
            "ALPACA_SECRET_KEY=SECCOMMENT\n"
        )
        env = write_env(tmp_path, content)
        api_key, secret_key = load_alpaca_keys(env)
        assert api_key == "PKCOMMENT"
        assert secret_key == "SECCOMMENT"

    def test_case_insensitive_keys(self, tmp_path):
        env = write_env(tmp_path, "alpaca_api_key=lowerapi\nalpaca_secret_key=lowersecret\n")
        api_key, secret_key = load_alpaca_keys(env)
        assert api_key == "lowerapi"
        assert secret_key == "lowersecret"

    def test_raises_file_not_found_when_file_missing(self, tmp_path):
        missing = tmp_path / "nonexistent.env"
        with pytest.raises(FileNotFoundError):
            load_alpaca_keys(missing)

    def test_raises_value_error_when_api_key_missing(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_SECRET_KEY=mysecret\n")
        with pytest.raises(ValueError, match="ALPACA_API_KEY"):
            load_alpaca_keys(env)

    def test_raises_value_error_when_secret_key_missing(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_API_KEY=PKTEST\n")
        with pytest.raises(ValueError, match="ALPACA_SECRET_KEY"):
            load_alpaca_keys(env)

    def test_raises_value_error_when_both_missing(self, tmp_path):
        env = write_env(tmp_path, "AV_KEYS=some_key\n")
        with pytest.raises(ValueError):
            load_alpaca_keys(env)

    def test_raises_value_error_when_api_key_empty(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_API_KEY=\nALPACA_SECRET_KEY=mysecret\n")
        with pytest.raises(ValueError, match="ALPACA_API_KEY"):
            load_alpaca_keys(env)

    def test_raises_value_error_when_secret_key_empty(self, tmp_path):
        env = write_env(tmp_path, "ALPACA_API_KEY=PKTEST\nALPACA_SECRET_KEY=\n")
        with pytest.raises(ValueError, match="ALPACA_SECRET_KEY"):
            load_alpaca_keys(env)

    def test_other_keys_in_file_do_not_interfere(self, tmp_path):
        content = (
            "AV_KEYS=KEY1,KEY2\n"
            "GROQ_API_KEY=gsk_abc\n"
            "TELEGRAM_BOT_TOKEN=realtoken\n"
            "ALPACA_API_KEY=PK_REAL\n"
            "TELEGRAM_CHAT_ID=55555\n"
            "ALPACA_SECRET_KEY=SEC_REAL\n"
        )
        env = write_env(tmp_path, content)
        api_key, secret_key = load_alpaca_keys(env)
        assert api_key == "PK_REAL"
        assert secret_key == "SEC_REAL"
