import asyncio
import json
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import discord
import pytz
from discord import Interaction, Webhook, Intents, Client, app_commands
from discord.app_commands import CommandTree
from parsedatetime import parsedatetime, Calendar
from pytz.tzinfo import StaticTzInfo, DstTzInfo

from config import app_conf
from util.basic_log import log_info, log_debug, log_warn

intents = Intents.default()
intents.message_content = True
discord_client: Client = discord.Client(intents=intents)
reminder_cmds: CommandTree = app_commands.CommandTree(discord_client)


@dataclass
class Reminder:
    runtime: str
    followup: str
    message: str
    author: int
    ping_you: bool = True

    def get_followup(self, ds_client: Client) -> Webhook:
        return Webhook.from_url(self.followup, client=ds_client, bot_token=app_conf.server.bot_token)

    def store(self, reminder_file: Path):
        with reminder_file.open(mode="a") as rfi:
            rfi.write(json.dumps(asdict(self)) + "\n")

    def get_runtime(self) -> datetime:
        return datetime.fromisoformat(self.runtime)


@discord_client.event
async def on_ready():
    log_info(f"Logged on as {discord_client.user}", on_ready.__name__)


async def before_serving():
    await discord_client.login(app_conf.server.bot_token)

    for guild in app_conf.server.get_sync_guilds():
        await reminder_cmds.sync(guild=guild)

    reminders: list[Reminder] = []
    with app_conf.server.get_reminder_file().open("r") as rfia:
        for li in rfia.readlines():
            r: Reminder = Reminder(**json.loads(li))
            if datetime.now(tz=pytz.UTC) < r.get_runtime():
                reminders.append(r)
                asyncio.ensure_future(send_reminder(r))

    if app_conf.server.clean_reminders_on_startup:
        app_conf.server.get_reminder_file().open("w").close()
        for rem in reminders:
            rem.store(app_conf.server.get_reminder_file())

    log_info(f"discord commands synced, {len(reminders)} stored reminders loaded, starting client",
             before_serving.__name__)
    await discord_client.connect()


async def send_reminder(reminder: Reminder):
    dt_now: datetime = datetime.now(tz=pytz.UTC)
    log_debug(f"reminder created ({reminder.runtime}): {reminder.message}", send_reminder.__name__)
    await asyncio.sleep((reminder.get_runtime() - dt_now).total_seconds())
    log_debug(f"sending reminder", send_reminder.__name__)

    author_ping: str = f" <@{reminder.author}>" if reminder.ping_you else ""
    await reminder.get_followup(discord_client).send(f"Reminder{author_ping}: {reminder.message}")
    log_info(f"reminder sent to {reminder.author}", send_reminder.__name__)


@reminder_cmds.command(name="remind", description="Add a reminder using natural language",
                       guilds=app_conf.server.get_sync_guilds())
async def set_reminder(interaction: Interaction, remind_at: str, message: str, tz: Optional[str] = "US/Pacific",
                       ping_you: Optional[bool] = True):
    try:

        dt_now: datetime = datetime.now(tz=pytz.UTC)
        msg_tz: StaticTzInfo | DstTzInfo = pytz.timezone(tz)

        msg_context_time: datetime = interaction.created_at.astimezone(msg_tz)

        cal: Calendar = parsedatetime.Calendar()
        parsed_time, flag = cal.parseDT(datetimeString=remind_at, sourceTime=msg_context_time, tzinfo=msg_tz)

        if flag == 0:
            log_warn(f"{remind_at} failed to parse", set_reminder.name)
            await interaction.response.send_message(f"I didn't understand the send time '{remind_at}'")
            return
        if parsed_time < dt_now + timedelta(seconds=app_conf.server.min_reminder_s):
            log_warn(f"{parsed_time.isoformat()} is in the past, no reminder", set_reminder.name)
            await interaction.response.send_message(
                f"the reminder time needs to be at least {app_conf.server.min_reminder_s}s in the future")
            return

        log_info(f"{remind_at} ({parsed_time.isoformat()} {(parsed_time - dt_now).total_seconds()}s): {message}",
                 set_reminder.name)

        reminder: Reminder = Reminder(parsed_time.isoformat(), interaction.followup.url, message, interaction.user.id,
                                      ping_you)
        reminder.store(app_conf.server.get_reminder_file())
        asyncio.ensure_future(send_reminder(reminder))

        await interaction.response.send_message(
            f"reminder set for '{remind_at}' at {parsed_time.strftime('%a %d %b %Y, %I:%M:%S%p')}")
        log_info("reminder registered", set_reminder.name)
    except Exception as e:
        log_info(str(e))
        await interaction.response.send_message(f"I didn't couldn't schedule that reminder :disappointed:")


@reminder_cmds.command(name="reminder_help", description="Print Help Text", guilds=app_conf.server.get_sync_guilds())
async def get_help(interaction: Interaction):
    help_text: str = ("/remind <remind_at> <msg> <ping_you (true)>: set a reminder for a future date\n"
                      + "\tremind_at: Reminder time, accepts somewhat natural language\n"
                      + "\tmsg: Reminder message (`@mentions` are allowed)\n"
                      + "\tping_you: whether to ping the reminder author, "
                      + "click `+1 option` to enable the parameter dropdown.\n"
                      + "\t\tExamples: 'in 4 hours', 'tomorrow at 9am', '8pm'\n"
                      + "/help: print help text")

    await interaction.response.send_message(help_text)


async def main():
    log_debug(f"Config: {json.dumps(asdict(app_conf))}")
    await before_serving()


if __name__ == "__main__":
    asyncio.run(main())
