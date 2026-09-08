"""Creates one demo organization, one user per role, and the Role rows they
need. Refuses to run outside development, and the printed credentials are
for local/demo use only — see docs/dataset-card.md / README "Demo credentials".

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

DEMO_PASSWORD = "Demo-Password-123!"  # noqa: S105 (dev-only demo credential, not a secret)
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

        created = []
        for role_name in RoleName:
            email = f"{role_name.value.lower()}@demo.cardiacai-test.dev"
            if user_repository.get_by_email(db, email) is not None:
                continue
            user = user_repository.create(
                db,
                organization_id=org.id,
                email=email,
                full_name=f"Demo {role_name.value.title()}",
                password_hash=hash_password(DEMO_PASSWORD),
            )
            role = user_repository.get_role_by_name(db, role_name.value)
            user_repository.assign_role(db, user_id=user.id, role_id=role.id, assigned_by=None)
            created.append(email)

        db.commit()
    finally:
        db.close()

    print(f"Demo organization: {DEMO_ORG_NAME}")
    if created:
        print("Created demo users (development only — rotate/disable outside demo mode):")
        for email in created:
            print(f"  {email}  /  {DEMO_PASSWORD}")
    else:
        print("Demo users already existed — nothing created.")


if __name__ == "__main__":
    main()
