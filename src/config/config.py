from dataclasses import dataclass
from pathlib import Path

import yaml
from discord import Object


@dataclass
class ServerConfig:
    app_id: int
    bot_token: str
    log_level: str
    sync_guilds: list[int]
    min_reminder_s: int
    reminder_file: str
    clean_reminders_on_startup: bool

    def get_sync_guilds(self) -> list[Object]:
        return [Object(gid) for gid in self.sync_guilds]

    def get_reminder_file(self) -> Path:
        return Path(self.reminder_file)


@dataclass
class AppConfig:
    server: ServerConfig


def init_config(conf_fi: Path) -> AppConfig:
    with open(conf_fi) as env:
        env_vals: dict = yaml.safe_load(env)

        server_conf: ServerConfig = ServerConfig(**env_vals["server"])

    return AppConfig(server_conf)
