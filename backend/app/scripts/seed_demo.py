"""Creates one demo organization, one user per role, and the Role rows they
need. Refuses to run outside development, and the printed credentials are
for local/demo use only — see README "Usuarios de prueba".

Passwords are deliberately trivial (per-role 4-digit PINs, not a real
password policy) — this is a local research prototype's demo data, not a
production credential; there is no password-complexity rule anywhere in
this codebase to bypass (see app/schemas/user.py).

Usage: python -m app.scripts.seed_demo
"""
import sys

from app.core.config import get_settings
from app.core.roles import RoleName
from app.core.security import hash_password
from app.db.session import get_session_factory
from app.models.organization import Organization
from app.models.role import Role
from app.repositories import user_repository

# Dev-only demo credentials, not secrets — one simple PIN per role, easy to
# remember while trying each role's view of the app.
DEMO_PASSWORDS: dict[RoleName, str] = {
    RoleName.ADMIN: "1111",
    RoleName.DOCTOR: "1234",
    RoleName.ANNOTATOR: "2222",
    RoleName.ML_ENGINEER: "3333",
    RoleName.MODEL_APPROVER: "4444",
    RoleName.AUDITOR: "5555",
}
DEMO_ORG_NAME = "CardiacAI Research Demo"


def main() -> None:
    settings = get_settings()
    if settings.environment == "production":
        print("Refusing to seed demo data: ENVIRONMENT=production", file=sys.stderr)
        sys.exit(1)

    session_factory = get_session_factory()
    db = session_factory()
    try:
        org = db.query(Organization).filter_by(name=DEMO_ORG_NAME).one_or_none()
        if org is None:
            org = Organization(name=DEMO_ORG_NAME)
            db.add(org)
            db.flush()

        for role_name in RoleName:
            if user_repository.get_role_by_name(db, role_name.value) is None:
                db.add(Role(name=role_name.value, description=f"{role_name.value} role"))
        db.flush()

        credentials = []
        for role_name in RoleName:
            email = f"{role_name.value.lower()}@demo.cardiacai-test.dev"
            password = DEMO_PASSWORDS[role_name]
            existing = user_repository.get_by_email(db, email)
            if existing is None:
                user = user_repository.create(
                    db,
                    organization_id=org.id,
                    email=email,
                    full_name=f"Demo {role_name.value.title()}",
                    password_hash=hash_password(password),
                )
            else:
                # Re-running the seed converges existing users to the
                # current DEMO_PASSWORDS mapping instead of silently
                # leaving whatever password they were created with.
                user = existing
                user.password_hash = hash_password(password)
            role = user_repository.get_role_by_name(db, role_name.value)
            user_repository.assign_role(db, user_id=user.id, role_id=role.id, assigned_by=None)
            credentials.append((email, password))

        db.commit()
    finally:
        db.close()

    print(f"Demo organization: {DEMO_ORG_NAME}")
    print("Demo users (development only — rotate/disable outside demo mode):")
    for email, password in credentials:
        print(f"  {email}  /  {password}")


if __name__ == "__main__":
    main()
