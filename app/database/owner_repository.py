"""
Owner / Fleet Manager repository and authentication database operations.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Optional

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError

ph = PasswordHasher()


def hash_password(password: str) -> str:
    """Hash a plaintext password using the Argon2id algorithm."""
    return ph.hash(password)


def verify_password(password: str, hashed_password: str) -> bool:
    """Verify a plaintext password against an Argon2id hash."""
    try:
        return ph.verify(hashed_password, password)
    except (VerifyMismatchError, VerificationError):
        return False


@dataclass(frozen=True)
class OwnerRecord:
    """Immutable representation of an active fleet owner/manager account."""
    owner_id: int
    name: str
    email: str
    password_hash: str
    created_at: str
    is_active: int


def _row_to_owner(row: Any) -> OwnerRecord:
    return OwnerRecord(
        owner_id=row["owner_id"],
        name=row["name"],
        email=row["email"],
        password_hash=row["password_hash"],
        created_at=row["created_at"],
        is_active=row["is_active"],
    )


class OwnerRepository:
    """Handles owner registration, credential verification, and account management."""

    def __init__(self, conn: Any) -> None:
        self._conn = conn

    def get_owner_by_id(self, owner_id: int) -> Optional[OwnerRecord]:
        """Fetch an active owner by primary key."""
        row = self._conn.execute(
            "SELECT * FROM owners WHERE owner_id = ? AND is_active = 1",
            (owner_id,),
        ).fetchone()
        if row is None:
            return None
        return _row_to_owner(row)

    def get_owner_by_email(self, email: str) -> Optional[OwnerRecord]:
        """Fetch an active owner by email address (case-insensitive)."""
        row = self._conn.execute(
            "SELECT * FROM owners WHERE LOWER(email) = LOWER(?) AND is_active = 1",
            (email.strip(),),
        ).fetchone()
        if row is None:
            return None
        return _row_to_owner(row)

    def is_email_registered(self, email: str) -> bool:
        """Check if an email address is already registered to an owner."""
        row = self._conn.execute(
            "SELECT owner_id FROM owners WHERE LOWER(email) = LOWER(?)",
            (email.strip(),),
        ).fetchone()
        return row is not None

    def create_owner(self, name: str, email: str, plain_password: str) -> int:
        """
        Create and persist a new fleet owner account.
        
        Raises
        ------
        ValueError
            If email is already registered or password length is < 8 characters.
        """
        clean_email = email.strip()
        if self.is_email_registered(clean_email):
            raise ValueError(f"Email '{clean_email}' is already registered.")

        if len(plain_password) < 8:
            raise ValueError("Password must be at least 8 characters long.")

        pwd_hash = hash_password(plain_password)
        now = datetime.now(timezone.utc).isoformat()

        cursor = self._conn.execute(
            """
            INSERT INTO owners (name, email, password_hash, created_at, is_active)
            VALUES (?, ?, ?, ?, 1)
            """,
            (name.strip(), clean_email, pwd_hash, now),
        )
        self._conn.commit()
        return cursor.lastrowid

    def authenticate_owner(self, email: str, plain_password: str) -> Optional[OwnerRecord]:
        """
        Authenticate an owner via email and password.
        
        Returns
        -------
        OwnerRecord or None
            Returns the owner record if credentials match, else None.
        """
        owner = self.get_owner_by_email(email)
        if owner is None:
            return None

        if not verify_password(plain_password, owner.password_hash):
            return None

        return owner

    def get_owner_count(self) -> int:
        """Return the total number of active registered fleet owners."""
        row = self._conn.execute("SELECT COUNT(*) FROM owners WHERE is_active = 1").fetchone()
        return row[0] if row else 0
