"""Authentification locale : le rôle de l'utilisateur vient de son compte, jamais de son choix.

Les mots de passe ne sont jamais stockés en clair : seul un hachage PBKDF2-SHA256 salé est conservé.
(En production, on utiliserait le SSO de l'entreprise : Azure AD, Okta… via OpenID Connect.)

Créer ou modifier un compte :
  python src/auth.py add ahmed employe
  python src/auth.py add salma rh
"""
import getpass
import hashlib
import hmac
import secrets
import sys
from pathlib import Path

import yaml

ITERATIONS = 200_000      # rend le cassage des mots de passe par force brute coûteux


def hash_password(password, salt=None):
    salt = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), ITERATIONS).hex()
    return salt, digest


def load_users(path):
    path = Path(path)
    if not path.exists():
        return {}
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get("users", {})


def authenticate(username, password, users):
    """Renvoie le rôle si l'identifiant et le mot de passe sont corrects, sinon None."""
    user = users.get(username.strip().lower())
    if not user:
        hash_password(password)              # même durée de calcul : ne révèle pas si le compte existe
        return None
    _, digest = hash_password(password, user["salt"])
    return user["role"] if hmac.compare_digest(digest, user["hash"]) else None


def add_user(path, username, role, password):
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.exists() else None
    data = data or {"users": {}}
    salt, digest = hash_password(password)
    data["users"][username.strip().lower()] = {"role": role, "salt": salt, "hash": digest}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=True), encoding="utf-8")


def main():
    if len(sys.argv) != 4 or sys.argv[1] != "add":
        sys.exit("Usage : python src/auth.py add <identifiant> <role>")
    with open("params.yaml", encoding="utf-8") as f:
        params = yaml.safe_load(f)
    _, username, role = sys.argv[1:]
    roles = params["rag"]["roles"]
    if role not in roles:
        sys.exit(f"Rôle inconnu : {role} (rôles possibles : {', '.join(roles)})")
    password = getpass.getpass(f"Mot de passe pour {username} (non affiché) : ")
    if len(password) < 8:
        sys.exit("Mot de passe trop court (8 caractères minimum).")
    add_user(params["auth"]["users_path"], username, role, password)
    print(f"Compte '{username}' enregistré avec le rôle '{role}'.")


if __name__ == "__main__":
    main()
