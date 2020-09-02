# SCP-079-CAPTCHA - Provide challenges for newly joined members
# Copyright (C) 2019-2020 SCP-079 <https://scp-079.org>
#
# This file is part of SCP-079-CAPTCHA.
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published
# by the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

import logging
import re
from copy import deepcopy
from subprocess import run, PIPE

from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from .. import glovar
from ..functions.captcha import send_static, user_captcha, user_captcha_qns
from ..functions.channel import get_debug_text, send_debug, share_data
from ..functions.command import delete_normal_command, delete_shared_command, command_error, get_command_context
from ..functions.command import get_command_type
from ..functions.config import conflict_config, get_config_text, qns_add, qns_remove, qns_show, start_qns
from ..functions.config import update_config
from ..functions.etc import code, code_block, general_link, get_int, get_now, get_readable_time, lang, mention_id
from ..functions.etc import message_link, random_str, thread
from ..functions.file import save
from ..functions.filters import authorized_group, captcha_group, class_e, from_user
from ..functions.filters import is_class_c, is_class_e, is_class_e_user, is_from_user, is_should_qns, test_group
from ..functions.group import delete_message
from ..functions.ids import init_user_id
from ..functions.markup import get_text_and_markup
from ..functions.telegram import forward_messages, get_group_info, get_start, send_message, send_report_message
from ..functions.user import add_start, get_uid, terminate_user_pass, terminate_user_succeed, terminate_user_undo_pass

# Enable logging
logger = logging.getLogger(__name__)


@Client.on_message(filters.incoming & filters.private & filters.command(["add"], glovar.prefix)
                   & from_user & class_e)
def add(client: Client, message: Message) -> bool:
    # Add a custom question
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        uid = message.from_user.id
        now = message.date or get_now()

        # Get group id
        gid = 0

        for group_id in list(glovar.questions):
            if now >= glovar.questions[group_id]["lock"] + 600:
                continue

            if glovar.questions[group_id]["aid"] != uid:
                continue

            gid = group_id
            break

        # Check the group id
        if not gid:
            return False

        # Get custom text
        text = get_command_type(message)

        # Check the command format
        if not text:
            return command_error(client, message, lang("action_qns_add"), lang("command_usage"), report=False)

        # Get key
        key = random_str(8)

        while glovar.questions[gid]["qns"].get(key):
            key = random_str(8)

        result = qns_add(client, message, gid, key, text)
    except Exception as e:
        logger.warning(f"Add error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()

    return result


@Client.on_message(filters.incoming & filters.group
                   & filters.command(["captcha"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def captcha(client: Client, message: Message) -> bool:
    # Send CAPTCHA request manually
    result = False

    glovar.locks["message"].acquire()

    try:
        # Basic data
        gid = message.chat.id

        # Check permission
        if not is_class_c(None, None, message):
            return False

        # Basic data
        now = message.date or get_now()
        r_message = message.reply_to_message
        aid = message.from_user.id

        if not r_message or not is_from_user(None, None, r_message):
            return False

        # Check pass
        if is_class_c(None, None, r_message) or is_class_e(None, None, r_message):
            return False

        if r_message.new_chat_members:
            user = r_message.new_chat_members[0]
        else:
            user = r_message.from_user

        if is_should_qns(gid):
            result = user_captcha_qns(
                client=client,
                message=r_message,
                gid=gid,
                user=user,
                mid=r_message.message_id,
                aid=aid
            )
        else:
            result = user_captcha(
                client=client,
                message=r_message,
                gid=gid,
                user=user,
                mid=r_message.message_id,
                now=now,
                aid=aid
            )
    except Exception as e:
        logger.warning(f"Captcha error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["config"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def config(client: Client, message: Message) -> bool:
    # Request CONFIG session
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        gid = message.chat.id
        aid = message.from_user.id
        mid = message.message_id

        # Check permission
        if not is_class_c(None, None, message):
            return False

        # Check command format
        command_type, command_context = get_command_context(message)

        if not command_type or not re.search(f"^{glovar.sender}$", command_type, re.I):
            return False

        now = get_now()

        # Check the config lock
        if now - glovar.configs[gid]["lock"] < 310:
            return command_error(client, message, lang("config_change"), lang("command_flood"))

        # Private check
        if command_context == "private":
            result = forward_messages(
                client=client,
                cid=glovar.logging_channel_id,
                fid=gid,
                mids=mid
            )

            if not result:
                return False

            text = (f"{lang('project')}{lang('colon')}{code(glovar.sender)}\n"
                    f"{lang('user_id')}{lang('colon')}{code(aid)}\n"
                    f"{lang('level')}{lang('colon')}{code(lang('config_create'))}\n"
                    f"{lang('rule')}{lang('colon')}{code(lang('rule_custom'))}\n")
            result = send_message(client, glovar.logging_channel_id, text, result.message_id)
        else:
            result = None

        # Set lock
        glovar.configs[gid]["lock"] = now
        save("configs")

        # Ask CONFIG generate a config session
        group_name, group_link = get_group_info(client, message.chat)
        share_data(
            client=client,
            receivers=["CONFIG"],
            action="config",
            action_type="ask",
            data={
                "project_name": glovar.project_name,
                "project_link": glovar.project_link,
                "group_id": gid,
                "group_name": group_name,
                "group_link": group_link,
                "user_id": aid,
                "private": command_context == "private",
                "config": glovar.configs[gid],
                "default": glovar.default_config
            }
        )

        # Send debug message
        text = get_debug_text(client, message.chat)
        text += (f"{lang('admin_group')}{lang('colon')}{code(message.from_user.id)}\n"
                 f"{lang('action')}{lang('colon')}{code(lang('config_create'))}\n")

        if result:
            text += f"{lang('evidence')}{lang('colon')}{general_link(result.message_id, message_link(result))}\n"

        thread(send_message, (client, glovar.debug_channel_id, text))

        result = True
    except Exception as e:
        logger.warning(f"Config error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()
        delete_shared_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group
                   & filters.command([f"config_{glovar.sender.lower()}"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def config_directly(client: Client, message: Message) -> bool:
    # Config the bot directly
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        gid = message.chat.id
        aid = message.from_user.id
        now = get_now()

        # Check permission
        if not is_class_c(None, None, message):
            return False

        # Get get the command
        command_type, command_context = get_command_context(message)

        # Check the command
        if not command_type:
            return command_error(client, message, lang("config_change"), lang("command_lack"))

        # Get the config
        new_config = deepcopy(glovar.configs[gid])

        # Show the config
        if command_type == "show":
            text = (f"{lang('admin_group')}{lang('colon')}{code(aid)}\n"
                    f"{lang('action')}{lang('colon')}{code(lang('config_show'))}\n"
                    f"{get_config_text(new_config)}\n")
            return thread(send_report_message, (30, client, gid, text))

        # Check the config lock
        if now - new_config["lock"] < 310:
            return command_error(client, message, lang("config_change"), lang("config_locked"))

        # Set the config to default status
        if command_type == "default":
            new_config = deepcopy(glovar.default_config)
            new_config["lock"] = now
            return update_config(client, message, new_config, "default")

        # Check the command format
        if not command_context:
            return command_error(client, message, lang("config_change"), lang("command_lack"))

        # Check the command type
        if command_type not in {"delete", "restrict", "ban", "forgive", "hint", "pass", "pin", "qns", "manual"}:
            return command_error(client, message, lang("config_change"), lang("command_type"))

        # New settings
        if command_context == "off":
            new_config[command_type] = False
        elif command_context == "on":
            new_config[command_type] = True
        else:
            return command_error(client, message, lang("config_change"), lang("command_para"))

        new_config = conflict_config(new_config, ["restrict", "ban"], command_type)
        new_config["default"] = False
        result = update_config(client, message, new_config, f"{command_type} {command_context}")
    except Exception as e:
        logger.warning(f"Config directly error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["custom"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def custom(client: Client, message: Message) -> bool:
    # Set custom text
    result = False

    glovar.locks["message"].acquire()

    try:
        # Basic data
        gid = message.chat.id
        aid = message.from_user.id

        # Check permission
        if not is_class_c(None, None, message):
            return True

        # Get the command
        command_type, command_context = get_command_context(message)

        # Text prefix
        text = (f"{lang('admin')}{lang('colon')}{code(aid)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('action_custom'))}\n")

        # Check command format
        if command_type not in {"correct", "flood", "manual", "multi", "nospam", "single", "static", "wrong"}:
            return command_error(client, message, lang("action_custom"), lang("command_usage"))

        # Show the config
        if not command_context:
            # Text prefix
            text = (f"{lang('admin')}{lang('colon')}{code(aid)}\n"
                    f"{lang('action')}{lang('colon')}{code(lang('action_show'))}\n"
                    f"{lang('type')}{lang('colon')}{code(lang(f'custom_{command_type}'))}\n")

            # Get the config
            result = glovar.custom_texts[gid].get(command_type) or lang("reason_none")
            text += (f"{lang('result')}{lang('colon')}" + code("-" * 16) + "\n\n"
                     f"{code_block(result)}\n")

            # Check the text
            if len(text) > 4000:
                text = code_block(result)

            # Send the report message
            return thread(send_report_message, (20, client, gid, text))

        # Config welcome
        command_context = command_context.strip()

        # Check the command_context
        mention_only_list = ["$mention_name", "$mention_id"]
        mention_all_list = ["$mention_name", "$mention_id", "$code_name", "$code_id"]
        mention_lack = (command_type in {"nospam"}
                        and all(mention not in command_context for mention in mention_only_list))
        mention_redundant = (command_type in {"flood", "static"}
                             and any(mention in command_context for mention in mention_all_list))
        too_long = command_type in {"correct", "wrong"} and len(command_context) > 140

        # Set the custom text
        if command_context != "off" and (mention_lack or mention_redundant):
            detail = (mention_lack and lang("mention_lack")) or lang("mention_redundant")
            return command_error(client, message, lang("action_custom"), lang("command_usage"), detail)
        elif command_context != "off" and too_long:
            return command_error(client, message, lang("action_custom"), lang("command_para"),
                                 lang("error_exceed_popup"))
        elif command_context != "off":
            glovar.custom_texts[gid][command_type] = command_context
        else:
            glovar.custom_texts[gid][command_type] = ""

        # Save the data
        save("custom_texts")

        # Send the debug message
        send_debug(
            client=client,
            gids=[gid],
            action=lang("action_custom"),
            aid=aid,
            more=lang(f"custom_{command_type}")
        )

        # Send the report message
        text += (f"{lang('type')}{lang('colon')}{code(lang(f'custom_{command_type}'))}\n"
                 f"{lang('status')}{lang('colon')}{code(lang('status_succeeded'))}\n")
        thread(send_report_message, (20, client, gid, text))

        result = True
    except Exception as e:
        logger.warning(f"Custom error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.private & filters.command(["edit"], glovar.prefix)
                   & from_user & class_e)
def edit(client: Client, message: Message) -> bool:
    # Edit a custom question
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        uid = message.from_user.id
        now = message.date or get_now()

        # Get group id
        gid = 0

        for group_id in list(glovar.questions):
            if now >= glovar.questions[group_id]["lock"] + 600:
                continue

            if glovar.questions[group_id]["aid"] != uid:
                continue

            gid = group_id
            break

        # Check the group id
        if not gid:
            return False

        # Get key and custom text
        key, text = get_command_context(message)

        # Check the command format
        if not key or not text:
            return command_error(client, message, lang("action_qns_edit"), lang("command_usage"), report=False)

        # Check the key
        if not glovar.questions[gid]["qns"].get(key):
            return command_error(client, message, lang("action_qns_edit"), lang("command_para"),
                                 lang("error_qns_none"), False)

        result = qns_add(client, message, gid, key, text, "edit")
    except Exception as e:
        logger.warning(f"Edit error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["pass"], glovar.prefix)
                   & captcha_group & ~test_group
                   & from_user & class_e)
def pass_captcha(client: Client, message: Message) -> bool:
    # Pass in CAPTCHA
    result = False

    glovar.locks["message"].acquire()

    try:
        # Basic data
        cid = message.chat.id
        aid = message.from_user.id
        mid = message.message_id

        if not message.reply_to_message or not message.reply_to_message.from_user:
            return False

        # Get the user id
        uid = get_uid(client, message)

        # Check the user status
        if not (uid
                and uid != aid
                and glovar.user_ids.get(uid, {})
                and glovar.user_ids[uid]["wait"]
                and glovar.user_ids[uid]["mid"]):
            return delete_message(client, cid, mid)

        # Let user pass
        terminate_user_succeed(
            client=client,
            uid=uid
        )

        # Send the report message
        text = (f"{lang('admin')}{lang('colon')}{mention_id(aid)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('action_pass'))}\n"
                f"{lang('user_id')}{lang('colon')}{mention_id(uid)}\n"
                f"{lang('status')}{lang('colon')}{code(lang('status_succeeded'))}\n")
        thread(send_report_message, (30, client, cid, text))

        # Send the debug message
        text = (f"{lang('project')}{lang('colon')}{general_link(glovar.project_name, glovar.project_link)}\n"
                f"{lang('admin')}{lang('colon')}{code(aid)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('action_pass'))}\n"
                f"{lang('user_id')}{lang('colon')}{code(uid)}\n")
        thread(send_message, (client, glovar.debug_channel_id, text))

        result = True
    except Exception as e:
        logger.warning(f"Pass captcha error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["pass"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def pass_group(client: Client, message: Message) -> bool:
    # Pass in group
    result = False

    glovar.locks["message"].acquire()

    try:
        # Basic data
        gid = message.chat.id

        # Check permission
        if not is_class_c(None, None, message):
            return True

        # Generate the report message's text
        aid = message.from_user.id
        text = f"{lang('admin')}{lang('colon')}{code(aid)}\n"

        # Proceed
        uid = get_uid(client, message)

        # Check user status
        if not uid or uid == aid or is_class_e_user(uid):
            return command_error(client, message, lang("action_pass"), lang("command_usage"))

        # Terminate the user
        if glovar.user_ids[uid]["pass"].get(gid, 0):
            terminate_user_undo_pass(
                client=client,
                uid=uid,
                gid=gid,
                aid=aid
            )
            text += (f"{lang('action')}{lang('colon')}{code(lang('action_undo_pass'))}\n"
                     f"{lang('user_id')}{lang('colon')}{mention_id(uid)}\n"
                     f"{lang('status')}{lang('colon')}{code(lang('status_succeeded'))}\n")
        elif glovar.pass_counts.get(gid, 0) < 100 and init_user_id(uid):
            glovar.pass_counts[gid] = glovar.pass_counts.get(gid, 0) + 1
            terminate_user_pass(
                client=client,
                uid=uid,
                gid=gid,
                aid=aid
            )
            text += (f"{lang('action')}{lang('colon')}{code(lang('action_pass'))}\n"
                     f"{lang('user_id')}{lang('colon')}{mention_id(uid)}\n"
                     f"{lang('status')}{lang('colon')}{code(lang('status_succeeded'))}\n")
        else:
            return False

        # Send the report message
        thread(send_report_message, (30, client, gid, text))

        result = True
    except Exception as e:
        logger.warning(f"Pass group error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["qns"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def qns(client: Client, message: Message) -> bool:
    # Request a custom questions setting session
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        gid = message.chat.id
        aid = message.from_user.id
        mid = message.message_id
        now = message.date or get_now()

        # Check permission
        if not is_class_c(None, None, message):
            return True

        # Check the group status
        if now < glovar.questions[gid]["lock"] + 600:
            aid = glovar.questions[gid]["aid"]
            return command_error(client, message, lang("action_qns_start"), lang("error_qns_occupied"),
                                 lang("detail_qns_occupied").format(aid))

        # Save evidence
        result = forward_messages(
            client=client,
            cid=glovar.logging_channel_id,
            fid=gid,
            mids=mid
        )

        if not result:
            return False

        text = (f"{lang('project')}{lang('colon')}{code(glovar.sender)}\n"
                f"{lang('user_id')}{lang('colon')}{code(aid)}\n"
                f"{lang('level')}{lang('colon')}{code(lang('config_create'))}\n"
                f"{lang('rule')}{lang('colon')}{code(lang('rule_custom'))}\n")
        result = send_message(client, glovar.logging_channel_id, text, result.message_id)

        # Save the data
        glovar.questions[gid]["lock"] = now
        glovar.questions[gid]["aid"] = aid

        for group_id in list(glovar.questions):
            if glovar.questions[group_id]["aid"] != aid:
                continue

            if group_id == gid:
                continue

            glovar.questions[group_id]["lock"] = 0
            glovar.questions[group_id]["aid"] = 0

        save("questions")

        # Add start status
        key = add_start(get_now() + 180, gid, aid, "qns")

        # Send the report message
        text = (f"{lang('admin')}{lang('colon')}{code(aid)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('action_qns_start'))}\n"
                f"{lang('description')}{lang('colon')}{code(lang('config_button'))}\n")
        markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        text=lang("config_go"),
                        url=get_start(client, key)
                    )
                ]
            ]
        )
        thread(send_report_message, (180, client, gid, text, None, markup))

        # Send debug message
        text = get_debug_text(client, message.chat)
        text += (f"{lang('admin_group')}{lang('colon')}{code(message.from_user.id)}\n"
                 f"{lang('action')}{lang('colon')}{code(lang('config_create'))}\n"
                 f"{lang('evidence')}{lang('colon')}{general_link(result.message_id, message_link(result))}\n")
        thread(send_message, (client, glovar.debug_channel_id, text))

        result = True
    except Exception as e:
        logger.warning(f"Qns error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.private & filters.command(["remove", "rm"], glovar.prefix)
                   & from_user & class_e)
def remove(client: Client, message: Message) -> bool:
    # Remove a custom question
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        uid = message.from_user.id
        now = message.date or get_now()

        # Get group id
        gid = 0

        for group_id in list(glovar.questions):
            if now >= glovar.questions[group_id]["lock"] + 600:
                continue

            if glovar.questions[group_id]["aid"] != uid:
                continue

            gid = group_id
            break

        # Check the group id
        if not gid:
            return False

        # Get key
        key = get_command_type(message)

        # Check the command format
        if not key:
            return command_error(client, message, lang("action_qns_remove"), lang("command_usage"), report=False)

        # Check the key
        if not glovar.questions[gid]["qns"].get(key):
            return command_error(client, message, lang("action_qns_remove"), lang("command_para"),
                                 lang("error_qns_none"), False)

        result = qns_remove(client, message, gid, key)
    except Exception as e:
        logger.warning(f"Remove error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()

    return result


@Client.on_message(filters.incoming & filters.private & filters.command(["show"], glovar.prefix)
                   & from_user & class_e)
def show(client: Client, message: Message) -> bool:
    # Show custom questions
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        uid = message.from_user.id
        now = message.date or get_now()

        # Get group id
        gid = 0

        for group_id in list(glovar.questions):
            if now >= glovar.questions[group_id]["lock"] + 600:
                continue

            if glovar.questions[group_id]["aid"] != uid:
                continue

            gid = group_id
            break

        # Check the group id
        if not gid:
            return False

        # Get key
        file = get_command_type(message)

        result = qns_show(client, message, gid, file == "file")
    except Exception as e:
        logger.warning(f"Show error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()

    return result


@Client.on_message(filters.incoming & filters.private & filters.command(["start", "help"], glovar.prefix)
                   & from_user)
def start(client: Client, message: Message) -> bool:
    # Process /start command in private chat
    result = False

    glovar.locks["config"].acquire()

    try:
        # Basic data
        cid = message.chat.id
        mid = message.message_id
        now = message.date or get_now()

        # Get start key
        key = get_command_type(message)

        # Start session
        if is_class_e_user(message.from_user) and key and glovar.starts.get(key):
            # Get until time
            until = glovar.starts[key]["until"]

            # Check the until time
            if now >= until:
                return False

            # Get action
            action = glovar.starts[key]["action"]

            # Proceed
            if action == "qns":
                return start_qns(client, message, key)

        # Check started ids
        if cid in glovar.started_ids:
            return False

        # Add to started ids
        glovar.started_ids.add(cid)

        # Check aio mode
        if glovar.aio:
            return False

        # Check start text
        if not glovar.start_text:
            return False

        # Generate the text and markup
        text, markup = get_text_and_markup(glovar.start_text)

        # Send the report message
        thread(send_message, (client, cid, text, mid, markup))

        result = True
    except Exception as e:
        logger.warning(f"Start error: {e}", exc_info=True)
    finally:
        glovar.locks["config"].release()

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["static"], glovar.prefix)
                   & ~captcha_group & ~test_group & authorized_group
                   & from_user)
def static(client: Client, message: Message) -> bool:
    # Send a new static hint message
    result = False

    glovar.locks["message"].acquire()

    try:
        # Basic data
        gid = message.chat.id
        aid = message.from_user.id

        # Check permission
        if not is_class_c(None, None, message):
            return True

        # Proceed
        description = lang("description_hint").format(glovar.time_captcha)
        hint_text = f"{lang('description')}{lang('colon')}{code(description)}\n"
        send_static(client, gid, hint_text)

        # Send the report message
        text = (f"{lang('admin')}{lang('colon')}{code(aid)}\n"
                f"{lang('action')}{lang('colon')}{code(lang('action_static'))}\n"
                f"{lang('status')}{lang('colon')}{code(lang('status_succeeded'))}\n")
        thread(send_report_message, (15, client, gid, text))

        result = True
    except Exception as e:
        logger.warning(f"Static error: {e}", exc_info=True)
    finally:
        glovar.locks["message"].release()
        delete_normal_command(client, message)

    return result


@Client.on_message(filters.incoming & filters.group & filters.command(["version"], glovar.prefix)
                   & test_group
                   & from_user)
def version(client: Client, message: Message) -> bool:
    # Check the program's version
    result = False

    try:
        # Basic data
        cid = message.chat.id
        aid = message.from_user.id
        mid = message.message_id

        # Get command type
        command_type = get_command_type(message)

        # Check the command type
        if command_type and command_type.upper() != glovar.sender:
            return False

        # Version info
        git_change = bool(run("git diff-index HEAD --", stdout=PIPE, shell=True).stdout.decode().strip())
        git_date = run("git log -1 --format='%at'", stdout=PIPE, shell=True).stdout.decode()
        git_date = get_readable_time(get_int(git_date), "%Y/%m/%d %H:%M:%S")
        git_hash = run("git rev-parse --short HEAD", stdout=PIPE, shell=True).stdout.decode()
        get_hash_link = f"https://github.com/scp-079/scp-079-{glovar.sender.lower()}/commit/{git_hash}"
        command_date = get_readable_time(message.date, "%Y/%m/%d %H:%M:%S")

        # Generate the text
        text = (f"{lang('admin')}{lang('colon')}{mention_id(aid)}\n\n"
                f"{lang('project')}{lang('colon')}{code(glovar.sender)}\n"
                f"{lang('version')}{lang('colon')}{code(glovar.version)}\n"
                f"{lang('git_change')}{lang('colon')}{code(git_change)}\n"
                f"{lang('git_hash')}{lang('colon')}{general_link(git_hash, get_hash_link)}\n"
                f"{lang('git_date')}{lang('colon')}{code(git_date)}\n"
                f"{lang('command_date')}{lang('colon')}{code(command_date)}\n")

        # Send the report message
        result = send_message(client, cid, text, mid)
    except Exception as e:
        logger.warning(f"Version error: {e}", exc_info=True)

    return result
