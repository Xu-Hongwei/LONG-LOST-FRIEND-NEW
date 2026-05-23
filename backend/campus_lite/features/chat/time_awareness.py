from __future__ import annotations

from datetime import datetime, timedelta, timezone


LOCAL_TZ = timezone(timedelta(hours=8))


def build_time_awareness(last_message_at: str | None, now: datetime | None = None) -> str:
    if not last_message_at:
        return ""
    previous = _parse_sqlite_datetime(last_message_at)
    if not previous:
        return ""
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    elapsed_seconds = (current - previous).total_seconds()
    if elapsed_seconds < 30 * 60:
        return ""
    elapsed_label = _elapsed_label(elapsed_seconds)
    if not elapsed_label:
        return ""
    current_local = current.astimezone(LOCAL_TZ)
    previous_local = previous.astimezone(LOCAL_TZ)
    return (
        "真实时间上下文（供角色自然感知，不是台词模板）：\n"
        f"- current_time: {_format_local_datetime(current_local)}\n"
        f"- last_message_at: {_format_local_datetime(previous_local)}\n"
        f"- elapsed_since_last_message: 约{elapsed_label}\n"
        f"- elapsed_bucket: {_elapsed_bucket(elapsed_seconds)}\n"
        "使用方式：根据真实时间差自然调整语气和承接方式；不必每次主动提时间，不要机械复述字段或时间戳，"
        "不要因为用户隔了一阵才来就自动推断关系变差。"
    )


def _parse_sqlite_datetime(value: str) -> datetime | None:
    text = value.strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        try:
            parsed = datetime.strptime(text, "%Y-%m-%d %H:%M:%S")
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _elapsed_label(seconds: float) -> str:
    minutes = int(seconds // 60)
    if minutes < 30:
        return ""
    if minutes < 60:
        return f"{minutes}分钟"
    hours = int(minutes // 60)
    if hours < 6:
        return f"{hours}小时"
    if hours < 48:
        return "半天到一天多"
    days = int(hours // 24)
    if days < 14:
        return f"{days}天"
    weeks = max(2, int(round(days / 7)))
    if weeks < 8:
        return f"{weeks}周"
    months = max(2, int(round(days / 30)))
    return f"{months}个月"


def _elapsed_bucket(seconds: float) -> str:
    hours = seconds / 3600
    if hours < 1:
        return "short_pause"
    if hours < 6:
        return "same_day_pause"
    if hours < 48:
        return "overnight_or_next_day"
    if hours < 24 * 14:
        return "days_later"
    if hours < 24 * 60:
        return "weeks_later"
    return "months_later"


def _format_local_datetime(value: datetime) -> str:
    return value.strftime("%Y-%m-%d %H:%M")
