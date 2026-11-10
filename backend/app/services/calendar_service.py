"""Google Calendar free/busy and event operations with a no-network test mode."""

import logging
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote
from zoneinfo import ZoneInfo

import httpx

from app.config import settings

logger = logging.getLogger(__name__)
GOOGLE_CALENDAR_API = "https://www.googleapis.com/calendar/v3"
CALENDAR_SCOPE = "https://www.googleapis.com/auth/calendar"


class CalendarServiceError(RuntimeError):
    """Calendar integration failed; callers must not confirm the appointment."""


class CalendarSlotUnavailable(CalendarServiceError):
    """The selected calendar slot is no longer available."""


def _access_token() -> str:
    credentials_file = settings.google_calendar_credentials_file
    if not credentials_file or not Path(credentials_file).is_file():
        raise CalendarServiceError(
            "GOOGLE_CALENDAR_CREDENTIALS_FILE must reference a service-account JSON file."
        )
    try:
        from google.auth.transport.requests import Request
        from google.oauth2.service_account import Credentials

        credentials = Credentials.from_service_account_file(
            credentials_file,
            scopes=[CALENDAR_SCOPE],
        )
        credentials.refresh(Request())
    except Exception as exc:
        logger.exception("Google Calendar authentication failed.")
        raise CalendarServiceError("Google Calendar authentication failed.") from exc
    if not credentials.token:
        raise CalendarServiceError("Google Calendar returned no access token.")
    return credentials.token


def _request(
    method: str,
    url: str,
    *,
    params: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    try:
        response = httpx.request(
            method,
            url,
            headers={
                "Authorization": f"Bearer {_access_token()}",
                "Content-Type": "application/json",
            },
            params=params,
            json=body,
            timeout=20.0,
        )
        if response.status_code == 409:
            raise CalendarSlotUnavailable(
                "The interviewer calendar could not accept this time."
            )
        response.raise_for_status()
        if not response.content:
            return {}
        data = response.json()
    except CalendarServiceError:
        raise
    except httpx.HTTPStatusError as exc:
        logger.error(
            "Google Calendar request failed with HTTP %s",
            exc.response.status_code,
        )
        raise CalendarServiceError(
            "Google Calendar could not complete the request."
        ) from exc
    except (httpx.RequestError, ValueError) as exc:
        logger.error("Google Calendar request failed due to a transport or response error.")
        raise CalendarServiceError(
            "Google Calendar could not complete the request."
        ) from exc
    if not isinstance(data, dict):
        raise CalendarServiceError("Google Calendar returned an invalid response.")
    return data


def get_busy_intervals(
    calendar_id: str,
    time_min: datetime,
    time_max: datetime,
    *,
    exclude_event_id: str | None = None,
) -> list[tuple[datetime, datetime]]:
    """Get interviewer busy ranges from Google Calendar, or none in test mode."""
    if settings.scheduling_test_mode:
        return []
    if exclude_event_id:
        calendar_url = (
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events"
        )
        page_token = ""
        intervals: list[tuple[datetime, datetime]] = []
        while True:
            params = {
                "timeMin": time_min.astimezone(timezone.utc).isoformat(),
                "timeMax": time_max.astimezone(timezone.utc).isoformat(),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": "2500",
            }
            if page_token:
                params["pageToken"] = page_token
            payload = _request("GET", calendar_url, params=params)
            items = payload.get("items", [])
            if not isinstance(items, list):
                raise CalendarServiceError("Google Calendar returned invalid events.")
            for item in items:
                if not isinstance(item, dict) or item.get("id") == exclude_event_id:
                    continue
                if item.get("status") == "cancelled":
                    continue
                try:
                    start = _calendar_event_datetime(item["start"])
                    end = _calendar_event_datetime(item["end"])
                except (KeyError, AttributeError, TypeError, ValueError) as exc:
                    raise CalendarServiceError(
                        "Google Calendar returned malformed events."
                    ) from exc
                intervals.append((start, end))
            next_page = payload.get("nextPageToken")
            if not isinstance(next_page, str) or not next_page:
                return intervals
            page_token = next_page

    payload = _request(
        "POST",
        f"{GOOGLE_CALENDAR_API}/freeBusy",
        body={
            "timeMin": time_min.astimezone(timezone.utc).isoformat(),
            "timeMax": time_max.astimezone(timezone.utc).isoformat(),
            "timeZone": settings.google_calendar_time_zone,
            "items": [{"id": calendar_id}],
        },
    )
    calendars = payload.get("calendars")
    calendar = calendars.get(calendar_id) if isinstance(calendars, dict) else None
    if not isinstance(calendar, dict):
        raise CalendarServiceError("Google Calendar returned no availability for the interviewer.")
    if calendar.get("errors"):
        raise CalendarServiceError("Google Calendar could not read interviewer availability.")
    busy = calendar.get("busy", [])
    if not isinstance(busy, list):
        raise CalendarServiceError("Google Calendar returned invalid busy intervals.")
    intervals: list[tuple[datetime, datetime]] = []
    try:
        for item in busy:
            start = datetime.fromisoformat(item["start"].replace("Z", "+00:00"))
            end = datetime.fromisoformat(item["end"].replace("Z", "+00:00"))
            if start.tzinfo is None or end.tzinfo is None:
                raise ValueError("Calendar returned a timezone-naive interval.")
            intervals.append((start, end))
    except (KeyError, AttributeError, TypeError, ValueError) as exc:
        raise CalendarServiceError("Google Calendar returned malformed busy intervals.") from exc
    return intervals


def _calendar_event_datetime(value: dict[str, Any]) -> datetime:
    event_time = value.get("dateTime")
    if isinstance(event_time, str):
        parsed = datetime.fromisoformat(event_time.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Calendar event datetime has no timezone.")
        return parsed
    event_date = value.get("date")
    if isinstance(event_date, str):
        day = date.fromisoformat(event_date)
        return datetime.combine(
            day,
            time.min,
            tzinfo=ZoneInfo(settings.google_calendar_time_zone),
        )
    raise ValueError("Calendar event has no start or end datetime.")


def _event_body(
    *,
    summary: str,
    description: str,
    start_at: datetime,
    end_at: datetime,
    location: str | None = None,
) -> dict[str, Any]:
    body = {
        "summary": summary,
        "description": description,
        "start": {
            "dateTime": start_at.astimezone(timezone.utc).isoformat(),
            "timeZone": settings.google_calendar_time_zone,
        },
        "end": {
            "dateTime": end_at.astimezone(timezone.utc).isoformat(),
            "timeZone": settings.google_calendar_time_zone,
        },
    }
    if location:
        body["location"] = location
    return body


def create_event(
    *,
    calendar_id: str,
    summary: str,
    description: str,
    start_at: datetime,
    end_at: datetime,
    location: str | None = None,
) -> str:
    """Create the calendar event, returning its event ID only after success."""
    if settings.scheduling_test_mode:
        from uuid import uuid4

        return f"test-{uuid4()}"
    event = _request(
        "POST",
        f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}/events",
        params={"sendUpdates": "none"},
        body=_event_body(
            summary=summary,
            description=description,
            start_at=start_at,
            end_at=end_at,
            location=location,
        ),
    )
    event_id = event.get("id")
    if not isinstance(event_id, str) or not event_id:
        raise CalendarServiceError("Google Calendar created no event ID.")
    return event_id


def update_event(
    *,
    calendar_id: str,
    event_id: str,
    summary: str,
    description: str,
    start_at: datetime,
    end_at: datetime,
    location: str | None = None,
) -> str:
    """Update an event; only report success after Google Calendar accepts it."""
    if settings.scheduling_test_mode:
        return event_id
    event = _request(
        "PUT",
        (
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}"
            f"/events/{quote(event_id, safe='')}"
        ),
        params={"sendUpdates": "none"},
        body=_event_body(
            summary=summary,
            description=description,
            start_at=start_at,
            end_at=end_at,
            location=location,
        ),
    )
    returned_id = event.get("id")
    if not isinstance(returned_id, str) or not returned_id:
        raise CalendarServiceError("Google Calendar returned no event ID after update.")
    return returned_id


def delete_event(calendar_id: str, event_id: str | None) -> None:
    """Delete an existing event; test-mode events never reach Google."""
    if not event_id or settings.scheduling_test_mode:
        return
    _request(
        "DELETE",
        (
            f"{GOOGLE_CALENDAR_API}/calendars/{quote(calendar_id, safe='')}"
            f"/events/{quote(event_id, safe='')}"
        ),
        params={"sendUpdates": "none"},
    )
