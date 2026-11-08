"""Tests de l'authentification : le rôle vient du compte, les mots de passe ne sont jamais en clair."""
from auth import add_user, authenticate, load_users


def make_users(tmp_path):
    path = tmp_path / "users.yaml"
    add_user(path, "Ahmed", "employe", "motdepasse-ahmed")
    add_user(path, "salma", "rh", "motdepasse-salma")
    return path, load_users(path)


def test_correct_password_gives_the_account_role(tmp_path):
    _, users = make_users(tmp_path)
    assert authenticate("ahmed", "motdepasse-ahmed", users) == "employe"
    assert authenticate("SALMA", "motdepasse-salma", users) == "rh"     # identifiant insensible à la casse


def test_wrong_password_or_unknown_user_is_rejected(tmp_path):
    _, users = make_users(tmp_path)
    assert authenticate("ahmed", "motdepasse-salma", users) is None
    assert authenticate("inconnu", "nimportequoi", users) is None


def test_an_employee_cannot_become_hr(tmp_path):
    _, users = make_users(tmp_path)
    assert authenticate("ahmed", "motdepasse-ahmed", users) != "rh"


def test_passwords_are_never_stored_in_clear(tmp_path):
    path, _ = make_users(tmp_path)
    content = path.read_text(encoding="utf-8")
    assert "motdepasse-ahmed" not in content and "motdepasse-salma" not in content
