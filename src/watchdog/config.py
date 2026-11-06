"""
Settings come from Lambda environment variables, which Terraform sets.
The defaults here are what I'd use for a small dev/test account.
"""

import os
from dataclasses import dataclass, field


def _list(value):
    return [v.strip() for v in value.split(",") if v.strip()]


def _bool(value):
    return value.strip().lower() in ("1", "true", "yes")


@dataclass(frozen=True)
class Settings:
    regions: list = field(default_factory=lambda: ["ap-south-1"])

    # Idle EC2: average CPU under this % for the whole lookback window...
    idle_cpu_avg_pct: float = 5.0
    # ...and never spiking above this %. A box that sleeps all day but runs a
    # nightly batch job at 90% is doing real work, so it shouldn't be flagged.
    idle_cpu_peak_pct: float = 30.0
    lookback_days: int = 7

    snapshot_max_age_days: int = 90
    stopped_min_days: int = 14

    table_name: str = ""
    topic_arn: str = ""
    notify_when_clean: bool = False
    history_days: int = 90

    schedule_tag_key: str = "Schedule"
    schedule_tag_value: str = "office-hours"
    dry_run: bool = False

    @classmethod
    def from_env(cls):
        env = os.environ
        return cls(
            regions=_list(env.get("REGIONS", "ap-south-1")),
            idle_cpu_avg_pct=float(env.get("IDLE_CPU_AVG_PCT", 5)),
            idle_cpu_peak_pct=float(env.get("IDLE_CPU_PEAK_PCT", 30)),
            lookback_days=int(env.get("LOOKBACK_DAYS", 7)),
            snapshot_max_age_days=int(env.get("SNAPSHOT_MAX_AGE_DAYS", 90)),
            stopped_min_days=int(env.get("STOPPED_MIN_DAYS", 14)),
            table_name=env.get("FINDINGS_TABLE", ""),
            topic_arn=env.get("ALERT_TOPIC_ARN", ""),
            notify_when_clean=_bool(env.get("NOTIFY_WHEN_CLEAN", "false")),
            history_days=int(env.get("HISTORY_DAYS", 90)),
            schedule_tag_key=env.get("SCHEDULE_TAG_KEY", "Schedule"),
            schedule_tag_value=env.get("SCHEDULE_TAG_VALUE", "office-hours"),
            dry_run=_bool(env.get("DRY_RUN", "false")),
        )
