import pytest

from mailflow import auth
from mailflow.store import Store

PASSWORD = "correct horse battery"
MINUTE = 60.0
HOUR = 3600.0


@pytest.fixture
def store():
    s = Store(":memory:")
    s.add_user("sipho@example.com", "Sipho", auth.hash_password(PASSWORD), is_admin=False)
    return s


def test_hash_is_not_the_password_and_verifies():
    stored = auth.hash_password(PASSWORD)
    assert PASSWORD not in stored
    assert stored.startswith("scrypt$")
    assert auth.verify_password(PASSWORD, stored)
    assert not auth.verify_password("correct horse batterY", stored)
    assert auth.hash_password(PASSWORD) != stored  # salted


def test_short_password_is_refused():
    with pytest.raises(ValueError):
        auth.check_password_rule("elevenchars")
    auth.check_password_rule("twelve chars")


def test_login_gives_a_session_that_finds_the_user(store):
    token, user = auth.login(store, " Sipho@Example.com ", PASSWORD, "1.2.3.4", now=0.0)
    assert user.email == "sipho@example.com"
    assert auth.session_user(store, token, now=MINUTE).name == "Sipho"
    assert token not in str(store.dump_sessions())  # only the token's hash is stored


def test_unknown_email_and_wrong_password_get_the_same_refusal(store):
    with pytest.raises(auth.LoginRefused) as unknown:
        auth.login(store, "nobody@example.com", PASSWORD, "1.2.3.4", now=0.0)
    with pytest.raises(auth.LoginRefused) as wrong:
        auth.login(store, "sipho@example.com", "wrong password!", "1.2.3.4", now=0.0)
    assert str(unknown.value) == str(wrong.value)


def test_five_failures_lock_the_account_for_15_minutes(store):
    for i in range(5):
        with pytest.raises(auth.LoginRefused):
            auth.login(store, "sipho@example.com", "wrong password!", f"10.0.0.{i}", now=i * MINUTE)
    with pytest.raises(auth.LoginRefused) as locked:
        auth.login(store, "sipho@example.com", PASSWORD, "10.0.0.9", now=5 * MINUTE)
    assert "15 minutes" in str(locked.value)
    token, user = auth.login(store, "sipho@example.com", PASSWORD, "10.0.0.9", now=20 * MINUTE)
    assert user.email == "sipho@example.com"


def test_unknown_emails_lock_the_same_way(store):
    for i in range(5):
        with pytest.raises(auth.LoginRefused):
            auth.login(store, "ghost@example.com", "whatever pass", f"10.0.0.{i}", now=0.0)
    with pytest.raises(auth.LoginRefused) as locked:
        auth.login(store, "ghost@example.com", "whatever pass", "10.0.0.9", now=1.0)
    assert "15 minutes" in str(locked.value)


def test_twenty_failures_from_one_ip_block_that_ip(store):
    for i in range(20):
        with pytest.raises(auth.LoginRefused):
            auth.login(store, f"guess{i}@example.com", "wrong password!", "6.6.6.6", now=float(i))
    with pytest.raises(auth.LoginRefused):
        auth.login(store, "sipho@example.com", PASSWORD, "6.6.6.6", now=30.0)
    token, _ = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=30.0)
    assert auth.session_user(store, token, now=31.0) is not None


def test_session_expires_after_12_idle_hours(store):
    token, _ = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=0.0)
    assert auth.session_user(store, token, now=11 * HOUR) is not None
    assert auth.session_user(store, token, now=22 * HOUR) is not None  # used at 11 h, so idle only 11 h
    assert auth.session_user(store, token, now=35 * HOUR) is None


def test_session_ends_7_days_after_login_even_when_used(store):
    token, _ = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=0.0)
    for hour in range(10, 24 * 7, 10):
        assert auth.session_user(store, token, now=hour * HOUR) is not None
    assert auth.session_user(store, token, now=24 * 7 * HOUR + 1) is None


def test_disabling_a_user_ends_their_sessions(store):
    token, user = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=0.0)
    store.set_active(user.id, False)
    assert auth.session_user(store, token, now=1.0) is None
    with pytest.raises(auth.LoginRefused):
        auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=2.0)


def test_password_change_ends_other_sessions(store):
    token, user = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=0.0)
    store.set_password(user.id, auth.hash_password("a brand new password"))
    assert auth.session_user(store, token, now=1.0) is None


def test_logout_ends_the_session(store):
    token, _ = auth.login(store, "sipho@example.com", PASSWORD, "1.2.3.4", now=0.0)
    auth.logout(store, token)
    assert auth.session_user(store, token, now=1.0) is None
    assert auth.session_user(store, "not-a-token", now=1.0) is None


def test_duplicate_email_is_refused(store):
    with pytest.raises(ValueError):
        store.add_user("SIPHO@example.com", "Other", auth.hash_password(PASSWORD), is_admin=False)
