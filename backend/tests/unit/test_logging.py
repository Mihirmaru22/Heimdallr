from app.logging_setup import redact


def test_secrets_are_redacted():
    line = 'login password=hunter2 token: abc.def Authorization: Bearer xyz123 key sk-or-v1-0123456789abcdef'
    out = redact(line)
    for secret in ("hunter2", "abc.def", "xyz123", "sk-or-v1-0123456789abcdef"):
        assert secret not in out
