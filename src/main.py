import asyncio
import json
from asyncio import Future
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

import discord
import pytz
from discord import Interaction, Intents, Client, app_commands
from discord.app_commands import CommandTree
from parsedatetime import parsedatetime, Calendar
from pytz.tzinfo import StaticTzInfo, DstTzInfo

from config import app_conf
from util.basic_log import log_info, log_debug, log_warn


@dataclass
class Reminder:
    runtime: str
    followup_chan: int
    message: str
    author: int
    ping_you: bool = True

    def get_followup_chan(self, ds_client: Client):
        return ds_client.get_channel(self.followup_chan)

    def store(self, reminder_file: Path):
        with reminder_file.open(mode="a") as rfi:
            rfi.write(json.dumps(asdict(self)) + "\n")

    def get_runtime(self) -> datetime:
        return datetime.fromisoformat(self.runtime)

    def get_safe_dict(self) -> dict:
        ret: dict = asdict(self)
        ret.pop("followup")
        return ret

    def list_rep(self) -> str:
        return f"{datetime.fromisoformat(self.runtime).strftime('%a %d %b %Y, %I:%M:%S%p')}: {self.message}"


intents = Intents.default()
intents.message_content = True
discord_client: Client = discord.Client(intents=intents)
reminder_cmds: CommandTree = app_commands.CommandTree(discord_client)
all_futures: dict[int, list[tuple[Future, Reminder]]] = {}


@discord_client.event
async def on_ready():
    log_info(f"Logged on as {discord_client.user}", on_ready.__name__)


def create_future(r: Reminder):
    reminder_future: Future = asyncio.ensure_future(send_reminder(r))

    fl = all_futures.get(r.author, [])
    fl.append((reminder_future, r))
    all_futures[r.author] = fl


def rewrite_all_reminders():
    reminders: list[Reminder] = [rt[1] for rtl in all_futures.values() for rt in rtl]
    app_conf.server.get_reminder_file().open("w").close()
    dt_now: datetime = datetime.now(pytz.UTC)
    for rem in reminders:
        if dt_now < rem.get_runtime():
            rem.store(app_conf.server.get_reminder_file())


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
                create_future(r)

    if app_conf.server.clean_reminders_on_startup:
        app_conf.server.get_reminder_file().open("w").close()
        for rem in reminders:
            rem.store(app_conf.server.get_reminder_file())

    log_info(f"discord commands synced, {len(reminders)} stored reminders loaded, starting client",
             before_serving.__name__)
    await discord_client.connect()


async def send_reminder(reminder: Reminder):
    try:
        dt_now: datetime = datetime.now(tz=pytz.UTC)
        log_debug(f"reminder created ({reminder.runtime}): {reminder.message}", send_reminder.__name__)
        await asyncio.sleep((reminder.get_runtime() - dt_now).total_seconds())
        log_debug(f"sending reminder", send_reminder.__name__)

        author_ping: str = f" <@{reminder.author}>" if reminder.ping_you else ""
        await reminder.get_followup_chan(discord_client).send(f"Reminder{author_ping}: {reminder.message}")
        # await reminder.get_followup(discord_client).send(f"Reminder{author_ping}: {reminder.message}")
        log_info(f"reminder sent to {reminder.author}", send_reminder.__name__)
    except Exception as e:
        log_info(str(e), send_reminder.__name__)


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

        reminder: Reminder = Reminder(parsed_time.isoformat(), interaction.channel_id, message, interaction.user.id,
                                      ping_you)
        reminder.store(app_conf.server.get_reminder_file())
        create_future(reminder)

        await interaction.response.send_message(
            f"reminder set for '{remind_at}' at {parsed_time.strftime('%a %d %b %Y, %I:%M:%S%p')}")
        log_info("reminder registered", set_reminder.name)
    except Exception as e:
        log_info(str(e))
        await interaction.response.send_message(f"I didn't couldn't schedule that reminder :disappointed:")


@reminder_cmds.command(name="reminder_list", description="Get the current reminders",
                       guilds=app_conf.server.get_sync_guilds())
async def list_reminders(interaction: Interaction):
    reminders: list[tuple[Future, Reminder]] = all_futures.get(interaction.user.id, [])
    dt_now: datetime = datetime.now(pytz.UTC)
    filter_reminders = [r for r in reminders if dt_now < r[1].get_runtime()]
    list_text = ("Reminders: \n"
                 + "\n".join([f"({i + 1}) {r[1].list_rep()}" for i, r in enumerate(filter_reminders)]))
    log_info(f"reminders listed for {interaction.user.id}", list_reminders.name)
    await interaction.response.send_message(list_text)


@reminder_cmds.command(name="delete_reminder", description="Delete a reminder by index",
                       guilds=app_conf.server.get_sync_guilds())
async def delete_reminder(interaction: Interaction, index: int):
    dt_now: datetime = datetime.now(pytz.UTC)
    idx = index - 1
    reminders: list[tuple[Future, Reminder]] = [r for r in dt_now < all_futures.get(interaction.user.id, []) if
                                                r[1].get_runtime()]

    if not (0 <= idx <= len(reminders)):
        await interaction.response.send_message(f"{index} isn't a valid ID")
    deleted = reminders.pop(idx)
    deleted[0].cancel()
    all_futures[interaction.user.id] = reminders
    rewrite_all_reminders()
    log_info(f"deleted reminder for {interaction.user.id}", delete_reminder.name)
    await interaction.response.send_message(f"Deleted {deleted[1].list_rep()}")


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
