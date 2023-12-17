from pathlib import Path

from config.config import init_config, AppConfig

app_conf: AppConfig = init_config(Path("env.yml"))
