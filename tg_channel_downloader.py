# !/usr/bin/env python3
import difflib
import os
import re
import time
import asyncio
import asyncio.subprocess
import logging
from telethon import TelegramClient, events, errors
from telethon.tl.types import MessageMediaWebPage

#***********************************************************************************#
api_id = 2135439   # your telegram api id
api_hash = 'aa38ea51ba2b4xxxxxxxf0231a6da91a'  # your telegram api hash
save_path = '/root/telegram'  # file save path
max_num = 5  # 同时下载数量
# filter chat id /过滤某些频道不下载
blacklist = []
#***********************************************************************************#

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    level=logging.WARNING)
logger = logging.getLogger(__name__)
queue = asyncio.Queue()


# 文件夹/文件名称处理
def validateTitle(title):
    r_str = r"[\/\\\:\*\?\"\<\>\|\n]"  # '/ \ : * ? " < > |'
    new_title = re.sub(r_str, "_", title)  # 替换为下划线
    return new_title


# 获取相册标题
async def get_group_caption(message):
    group_caption = ""
    entity = await client.get_entity(message.to_id)
    async for msg in client.iter_messages(entity=entity, reverse=True, offset_id=message.id - 9, limit=10):
        if msg.grouped_id == message.grouped_id:
            if msg.text != "":
                group_caption = msg.text
                return group_caption
    return group_caption


# 获取本地时间
def get_local_time():
    return time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())


# 判断相似率
def get_equal_rate(str1, str2):
    return difflib.SequenceMatcher(None, str1, str2).quick_ratio()


async def worker(name):
    while True:
        queue_item = await queue.get()
        message = queue_item[0]
        chat_title = queue_item[1]
        entity = queue_item[2]
        file_name = queue_item[3]
        dirname = validateTitle(f'{chat_title}({entity.id})')
        datetime_dir_name = message.date.strftime("%Y年%m月")
        file_save_path = os.path.join(save_path, dirname, datetime_dir_name)
        if not os.path.exists(file_save_path):
            os.makedirs(file_save_path)
        # 判断文件是否在本地存在
        if file_name in os.listdir(file_save_path):
            os.remove(os.path.join(file_save_path, file_name))
        print(f"{get_local_time()} 开始下载： {chat_title} - {file_name}")
        try:
            loop = asyncio.get_event_loop()
            task = loop.create_task(client.download_media(
                message, os.path.join(file_save_path, file_name)))
            await asyncio.wait_for(task, timeout=3600)
            print(f"{get_local_time()} 下载完成： {chat_title} - {file_name}")
        except (errors.FileReferenceExpiredError, asyncio.TimeoutError):
            logging.warning(f'{get_local_time()} - {file_name} 出现异常，重新尝试下载！')
            async for new_message in client.iter_messages(entity=entity, offset_id=message.id - 1, reverse=True,
                                                          limit=1):
                await queue.put((new_message, chat_title, entity, file_name))
        except Exception as e:
            print(f"{get_local_time()} - {file_name} {e}")
        finally:
            queue.task_done()


@events.register(events.NewMessage())
async def all_chat_download(update):
    message = update.message
    if message.media:
        chat_id = update.message.to_id
        entity = await client.get_entity(chat_id)
        if entity.id in blacklist:
            return
        chat_title = entity.title
        # 如果是一组媒体
        caption = await get_group_caption(message) if (
            message.grouped_id and message.text == "") else message.text
        # 如果文件文件名不是空字符串，则进行过滤和截取，避免文件名过长导致的错误
        caption = "" if caption == "" else f'{validateTitle(caption)} - '[:50]
        file_name = ''
        # 如果是文件
        if message.document:
            try:
                if type(message.media) == MessageMediaWebPage:
                    return
                if message.media.document.mime_type == "image/webp":
                    file_name = f'{message.media.document.id}.webp'
                if message.media.document.mime_type == "application/x-tgsticker":
                    file_name = f'{message.media.document.id}.tgs'
                for i in message.document.attributes:
                    try:
                        file_name = i.file_name
                    except:
                        continue
                if file_name == '':
                    file_name = f'{message.id} - {caption}.{message.document.mime_type.split("/")[-1]}'
                else:
                    # 如果文件名中已经包含了标题，则过滤标题
                    if get_equal_rate(caption, file_name) > 0.6:
                        caption = ""
                    file_name = f'{message.id} - {caption}{file_name}'
            except:
                print(message.media)
        elif message.photo:
            file_name = f'{message.id} - {caption}{message.photo.id}.jpg'
        else:
            return
        await queue.put((message, chat_title, entity, file_name))


if __name__ == '__main__':
    client = TelegramClient('telegram_channel_downloader', api_id, api_hash).start()
    client.add_event_handler(all_chat_download)
    tasks = []
    try:
        for i in range(max_num):
            loop = asyncio.get_event_loop()
            task = loop.create_task(worker(f'worker-{i}'))
            tasks.append(task)
        print('Successfully started (Press Ctrl+C to stop)')
        client.run_until_disconnected()
    finally:
        for task in tasks:
            task.cancel()
        client.disconnect()
        print('Stopped!')
