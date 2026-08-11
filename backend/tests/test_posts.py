"""Local post persistence and editing behavior."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from app.main import app
from tests.helpers import create_post, future_local_time


def test_create_and_retrieve_draft(client: TestClient) -> None:
    created = create_post(client)

    assert created.status_code == 201
    payload = created.json()
    assert payload["caption"] == "A locally managed post"
    assert payload["status"] == "draft"
    assert payload["display_timezone"] == "Asia/Dhaka"
    assert payload["scheduled_for_utc"].endswith("Z")

    retrieved = client.get(f"/api/posts/{payload['id']}")
    assert retrieved.status_code == 200
    assert retrieved.json()["id"] == payload["id"]


def test_list_posts_is_newest_first(client: TestClient) -> None:
    first = create_post(client, caption="First").json()
    second = create_post(client, caption="Second").json()

    response = client.get("/api/posts")

    assert response.status_code == 200
    assert response.json()["total"] == 2
    assert [item["id"] for item in response.json()["items"]] == [
        second["id"],
        first["id"],
    ]


def test_update_resets_post_to_draft(client: TestClient) -> None:
    post = create_post(client).json()
    scheduled = client.post(f"/api/posts/{post['id']}/schedule")
    assert scheduled.status_code == 200

    new_time = future_local_time(days=2)
    response = client.patch(
        f"/api/posts/{post['id']}",
        json={
            "caption": "Edited caption",
            "scheduled_for_local": new_time,
            "timezone": "Asia/Dhaka",
        },
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["caption"] == "Edited caption"
    assert payload["status"] == "draft"
    assert payload["scheduled_for_local"].startswith(new_time)
    assert len(payload["attempts"]) == 1


def test_unknown_post_returns_structured_404(client: TestClient) -> None:
    response = client.get("/api/posts/00000000-0000-4000-8000-000000000000")

    assert response.status_code == 404
    assert response.json() == {
        "error": {"code": "POST_NOT_FOUND", "message": "Post not found."}
    }


def test_post_persists_across_application_restart() -> None:
    with TestClient(app) as first_client:
        post = create_post(first_client, caption="Persistent post").json()
        image_response = first_client.get(post["image_url"])
        assert image_response.status_code == 200

    with TestClient(app) as restarted_client:
        response = restarted_client.get(f"/api/posts/{post['id']}")
        persisted_image = restarted_client.get(post["image_url"])

    assert response.status_code == 200
    assert response.json()["caption"] == "Persistent post"
    assert persisted_image.status_code == 200
    assert persisted_image.content


def test_past_schedule_is_rejected(client: TestClient) -> None:
    past = datetime.now(ZoneInfo("Asia/Dhaka")) - timedelta(minutes=1)
    response = create_post(
        client,
        scheduled_for_local=past.strftime("%Y-%m-%dT%H:%M"),
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCHEDULE"


def test_malformed_schedule_is_rejected(client: TestClient) -> None:
    response = create_post(client, scheduled_for_local="not-a-date")

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "INVALID_SCHEDULE"
