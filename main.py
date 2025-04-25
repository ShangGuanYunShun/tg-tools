import os
import yaml
import asyncio
import logging
from telethon.sync import TelegramClient
from telethon.errors import SessionPasswordNeededError
from telethon.sessions import StringSession
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import requests
from telethon.tl import functions
from telethon.tl.types import PeerUser
from telethon import TelegramClient

CONFIG_FILE = "config.yaml"


def load_config():
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return yaml.safe_load(f)
    except Exception as e:
        logging.error(f"读取配置文件失败: {e}")
        raise


def setup_logging(level):
    log_level = getattr(logging, level.upper(), logging.DEBUG)
    logging.basicConfig(
        format='%(asctime)s - %(levelname)s - %(message)s',
        level=log_level
    )
    print(f"日志级别已设置为 {level.upper()}")


def send_bot_notification(bot_token, chat_id, message):
    try:
        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        payload = {
            "chat_id": chat_id,
            "text": message,
            "parse_mode": "Markdown"
        }
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            logging.error(f"Bot 通知失败: {response.text}")
    except Exception as e:
        logging.error(f"Bot 通知异常: {e}")


async def send_message(client, channel, message, notify_cfg=None, channel_name=None, task_type=None):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    try:
        logging.info(f"正在向频道 {channel} 发送消息: {message}")
        await client.send_message(channel, message)
        log = f"[✓] {now} 已向【{channel_name or channel}】发送[{task_type or '默认'}]消息：{message}"
        logging.info(log)
        if notify_cfg:
            msg = (
                f"✅ 发送消息成功（{task_type or '未指定类型'}）\n"
                f"频道: {channel_name or channel}\n"
                f"链接: {channel}\n"
                f"消息: {message}\n"
                f"时间: {now}"
            )
            send_bot_notification(notify_cfg["bot_token"], notify_cfg["chat_id"], msg)
    except Exception as e:
        err_log = f"[✗] {now} 向【{channel_name or channel}】发送[{task_type or '默认'}]失败：{e}"
        logging.error(err_log)
        if notify_cfg:
            msg = (
                f"❌ 发送消息失败（{task_type or '未指定类型'}）\n"
                f"频道: {channel_name or channel}\n"
                f"链接: {channel}\n"
                f"错误: {e}\n"
                f"时间: {now}"
            )
            send_bot_notification(notify_cfg["bot_token"], notify_cfg["chat_id"], msg)


async def keep_alive(client):
    while True:
        await asyncio.sleep(600)  # 每60秒触发一次
        try:
            await client(functions.PingRequest(ping_id=12345))
            logging.debug("Sent keep-alive ping")
        except Exception as e:
            logging.error(f"Keep-alive failed: {e}")


async def main():
    try:
        print("正在加载配置文件...")
        config = load_config()
        print(config)

        # 从配置文件中获取日志级别并设置
        log_level = config["logging"].get("level", "DEBUG")
        setup_logging(log_level)

        api_id = config["telegram"]["api_id"]
        api_hash = config["telegram"]["api_hash"]
        session_name = config["telegram"].get("session_name", "tg_session")
        password = config["telegram"].get("password", "")
        phone = config["telegram"].get("phone", "")
        code = config["telegram"].get("code", "")

        tasks = config.get("tasks", [])
        logging.debug(f'{tasks}')
        notify_cfg = config.get("bot_notify", None)

        proxy = None
        proxy_config = config.get("proxy")

        if proxy_config:
            type = proxy_config.get("type")  # socks5 / http / socks4
            hostname = proxy_config.get("host")
            port = proxy_config.get("port")
            if type and hostname and port:
                proxy = (type, hostname, port)
                logging.debug(f"使用代理连接: {type}://{hostname}:{port}")

        logging.debug("正在初始化 TelegramClient...")
        if not os.path.exists(f"{session_name}.session"):
            logging.debug("session 文件不存在，正在进行登录操作...")
            # 使用代理连接
            if proxy:
                client = TelegramClient('None', api_id, api_hash,
                                        proxy=proxy,
                                        timeout=20,
                                        connection_retries=5,
                                        auto_reconnect=True,
                                        retry_delay=3)
            else:
                client = TelegramClient('None', api_id, api_hash)
            await client.start(phone=phone, code_callback=lambda: code)
            logging.info("登录成功，session 已生成！")
        else:
            logging.info("使用现有的 session 登录...")
            # 使用代理连接
            if proxy:
                client = TelegramClient(session_name, api_id, api_hash,
                                        proxy=proxy,
                                        timeout=20,
                                        connection_retries=5,
                                        auto_reconnect=True,
                                        retry_delay=3)
            else:
                client = TelegramClient(session_name, api_id, api_hash)
        logging.debug("初始化 TelegramClient完成")

        asyncio.create_task(keep_alive(client))
        scheduler = AsyncIOScheduler()
        for task in tasks:
            trigger = CronTrigger.from_crontab(task["cron"])
            scheduler.add_job(
                send_message, trigger,
                args=[client, task["channel"], task["message"], notify_cfg, task.get("channel_name"), task.get("type")]
            )
            logging.info(
                f"已添加任务：频道={task.get('channel_name', task['channel'])}，类型={task.get('type')}，cron={task['cron']}")

        scheduler.start()
        logging.info("启动调度器，等待任务执行...")
        await asyncio.Event().wait()

    except Exception as e:
        logging.error(f"程序发生错误: {e}")


if __name__ == "__main__":
    asyncio.run(main())
