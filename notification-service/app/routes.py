from datetime import datetime, timezone

from fastapi import APIRouter, Query, Request, status

from app.database import get_conn
from app.errors import ApiError
from app.models import NotificationCreate, NotificationResponse

router = APIRouter()


@router.post(
    "/api/v1/notifications",
    response_model=NotificationResponse,
    status_code=status.HTTP_201_CREATED,
)
def create_notification(
    notification: NotificationCreate,
    request: Request,
):
    created_at = (
        datetime.now(timezone.utc)
        .isoformat(timespec="seconds")
        .replace("+00:00", "Z")
    )

    with get_conn() as connection:
        cursor = connection.execute(
            """
            INSERT INTO notifications
                (recipient_id, type, message, created_at)
            VALUES (?, ?, ?, ?)
            """,
            (
                notification.recipient_id,
                notification.type,
                notification.message,
                created_at,
            ),
        )

        notification_id = cursor.lastrowid

        saved = connection.execute(
            """
            SELECT id, recipient_id, type, message, created_at
            FROM notifications
            WHERE id = ?
            """,
            (notification_id,),
        ).fetchone()

    # This is a simulated send, not a real email or external API call.
    print(
        f"[NOTIFY] candidate {saved['recipient_id']} "
        f"{saved['type']}: {saved['message']}"
    )

    return dict(saved)


@router.get(
    "/api/v1/notifications",
    response_model=list[NotificationResponse],
)
def list_notifications(
    recipient_id: int | None = Query(default=None),
):
    with get_conn() as connection:
        if recipient_id is None:
            rows = connection.execute(
                """
                SELECT id, recipient_id, type, message, created_at
                FROM notifications
                ORDER BY id DESC
                """
            ).fetchall()
        else:
            rows = connection.execute(
                """
                SELECT id, recipient_id, type, message, created_at
                FROM notifications
                WHERE recipient_id = ?
                ORDER BY id DESC
                """,
                (recipient_id,),
            ).fetchall()

    return [dict(row) for row in rows]