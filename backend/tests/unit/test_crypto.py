import pytest
from cryptography.exceptions import InvalidTag

from mahlzeit.security import crypto, passwords, tokens


class TestEncryption:
    def test_roundtrip(self) -> None:
        blob = crypto.encrypt(b"secret", aad=b"ctx")
        assert b"secret" not in blob
        assert crypto.decrypt(blob, aad=b"ctx") == b"secret"

    def test_nonce_is_random(self) -> None:
        assert crypto.encrypt(b"same") != crypto.encrypt(b"same")

    def test_tampering_is_detected(self) -> None:
        blob = bytearray(crypto.encrypt(b"secret"))
        blob[-1] ^= 1
        with pytest.raises(InvalidTag):
            crypto.decrypt(bytes(blob))

    def test_wrong_context_is_rejected(self) -> None:
        with pytest.raises(InvalidTag):
            crypto.decrypt(crypto.encrypt(b"secret", aad=b"a"), aad=b"b")

    def test_wrong_key_is_rejected(self) -> None:
        with pytest.raises(InvalidTag):
            crypto.decrypt(crypto.encrypt(b"secret"), key=crypto.new_key())

    @pytest.mark.parametrize("key", ["", "c2hvcnQ"])
    def test_missing_or_short_key(self, key: str) -> None:
        with pytest.raises(crypto.EncryptionKeyMissing):
            crypto.encrypt(b"x", key=key)


class TestPasswords:
    def test_hash_is_argon2id(self) -> None:
        assert passwords.hash_password("correct horse").startswith("$argon2id$")

    def test_verify(self) -> None:
        h = passwords.hash_password("correct horse")
        assert passwords.verify_password(h, "correct horse")
        assert not passwords.verify_password(h, "wrong horse")
        assert not passwords.verify_password(None, "correct horse")
        assert not passwords.verify_password("garbage", "correct horse")


class TestTokens:
    def test_tokens_are_long_and_hashed(self) -> None:
        token = tokens.new_token()
        assert len(token) >= 43
        assert len(tokens.hash_token(token)) == 64
        assert tokens.hash_token(token) == tokens.hash_token(token)
