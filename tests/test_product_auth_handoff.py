from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return (ROOT / path).read_text()


def test_login_preserves_product_destination_for_artist_signup():
    login = read("templates/login.html")
    assert "request.args.get('next')" in login
    assert "url_for('signup', next=return_to)" in login
    assert "RETURN TO TOUR." in login


def test_signup_preserves_and_returns_to_safe_product_destination():
    signup = read("templates/signup.html")
    assert "url_for('signup', next=return_to)" in signup
    assert "url_for('login', next=return_to)" in signup
    assert "window.location.replace(target)" in signup
    assert "safeLocal" in signup
    assert "value.indexOf('//') !== 0" in signup
    assert "value.indexOf('\\\\') === -1" in signup


def test_tour_signup_keeps_shared_identity_but_product_local_landing():
    signup = read("templates/signup.html")
    assert "TOUR · SHARED STREET BANKER IDENTITY" in signup
    assert "Create Account & Open TOUR" in signup
    assert "You are not sent through the agent system." in signup
    assert "Invited crew can still join through their invitation." in signup
