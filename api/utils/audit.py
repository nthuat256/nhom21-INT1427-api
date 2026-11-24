from sqlalchemy.orm import Session

from api.models import AuditLog, User


def record_audit(
    db: Session,
    actor: User | None,
    action: str,
    entity_type: str,
    entity_id: str | None,
    details: dict | None = None,
) -> None:
    db.add(AuditLog(
        actor_id=actor.id if actor else None,
        action=action,
        entity_type=entity_type,
        entity_id=entity_id,
        details=details,
    ))
