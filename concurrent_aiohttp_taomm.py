#!/usr/bin/env python3
"""
Python version: > 3.4
Dependence: aiohttp async_timeout requests BeautifulSoup

爬虫类
从淘女郎网站（https://mm.taobao.com）获取图片链接并下载，按照地区、相册名、姓名分类
"""

import contextlib
import os
import re
import json
import aiohttp
import asyncio
import async_timeout
import time

from bs4 import BeautifulSoup

FIRST_PAGE = 1
TIMEOUT = 60
CONCURRENT_LEVEL = 20
MAX_USER_PAGE = 2
MAX_ALBUM_PAGE = 2
MAX_PHOTO_PAGE = 2

# 淘女郎列表页面
user_list = 'https://mm.taobao.com/json/request_top_list.htm?page={}'

# 淘女郎信息页
user_info = 'https://mm.taobao.com/self/info/model_info_show.htm?user_id={}'

# 淘女郎相册列表页面
album_list = 'https://mm.taobao.com/self/album/open_album_list.htm?user_id={}&page={}'

# 淘女郎相册json
photo_list = 'https://mm.taobao.com/album/json/get_album_photo_list.htm?user_id={}&album_id={}&page={}'


@contextlib.contextmanager
def timer():
    start = time.time()
    yield
    print('run in {:.1f} seconds'.format(time.time() - start))


class Photo:
    def __init__(self, id, url, album_name, user_name, location, session):
        self._id = id
        self._url = 'https:' + url
        self._user_name = user_name
        self._album_name = album_name
        self._location = location
        self._session = session
        self._path = os.path.join(os.getcwd(), 'taomm', self._location, self._user_name, self._album_name)
        os.makedirs(self._path, exist_ok=True)

    async def __await__(self):
        image = await self.fetch(self._url)
        # print(self._url)
        await self._session.loop.run_in_executor(None, self.save, image)

    async def fetch(self, url):
        with async_timeout.timeout(TIMEOUT):
            async with self._session.get(url) as response:
                return await response.read()

    def save(self, image):
        path = self._path + '\\' + self._id + '.jpg'
        with open(path, 'wb') as f:
            f.write(image)
        print(path)

    def __repr__(self):
        return '<Photo(id={})>'.format(self._id)


class Album:
    def __init__(self, id, name, user_id, user_name, location, *, session):
        self._id = id
        self._user_id = user_id
        self._name = name
        self._user_name = user_name
        self._location = location
        self._photos = []
        self._session = session

    async def __await__(self):
        await self.get_photos()
        print(self)
        await asyncio.wait(self._photos)

    async def get_page_nums(self):
        # get users list page nums
        photo_list_url = photo_list.format(self._user_id, self._id, FIRST_PAGE)
        resp = await self.fetch(photo_list_url)
        return self.parse_page_nums(resp)

    async def get_photo_by_page(self, page):
        photo_list_url = photo_list.format(self._user_id, self._id, page)
        resp = await self.fetch(photo_list_url)
        self.parse_photo_url(resp)

    async def fetch(self, url):
        with async_timeout.timeout(TIMEOUT):
            async with self._session.get(url) as response:
                return await response.text()

    @staticmethod
    def parse_page_nums(resp):
        json_data = json.loads(resp)
        pages = int(json_data['totalPage'])
        return pages

    def parse_photo_url(self, resp):
        json_data = json.loads(resp)
        photos = json_data['picList']
        for photo in photos:
            self._photos.append(Photo(photo['picId'],
                                      photo['picUrl'],
                                      self._name,
                                      self._user_name,
                                      self._location,
                                      session=self._session))

    async def get_photos(self):
        # 获取照片页面数
        pages = await self.get_page_nums()
        # 获取照片列表
        tasks = [self.get_photo_by_page(page + 1) for page in range(min(MAX_PHOTO_PAGE, pages) or pages)]
        await asyncio.wait(tasks)

    def __repr__(self):
        return '<Album(id={} name={} user={})>'.format(self._id, self._name, self._user_name)


class User:
    def __init__(self, id, *, session):
        self._id = id
        self._name = ''
        self._location = ''
        self._albums = []
        self._session = session

    async def __await__(self):
        # 获取用户信息
        await self.get_info()
        # 获取相册列表
        await self.get_albums()
        print(self)
        await asyncio.wait(self._albums)

    async def get_page_nums(self):
        # get users list page nums
        album_list_url = album_list.format(self._id, FIRST_PAGE)
        resp = await self.fetch(album_list_url)
        return self.parse_page_nums(resp)

    async def get_album_by_page(self, page):
        album_list_url = album_list.format(self._id, page)
        resp = await self.fetch(album_list_url)
        self.parse_album_id(resp)

    async def fetch(self, url):
        with async_timeout.timeout(TIMEOUT):
            async with self._session.get(url) as response:
                return await response.text()

    @staticmethod
    def parse_page_nums(resp):
        soup = BeautifulSoup(resp, 'lxml')
        pages = int(soup.find('input', id='J_Totalpage').get('value', 0))
        return pages

    def parse_user_info(self, resp):
        soup = BeautifulSoup(resp, 'lxml')
        self._name = soup.find('ul', class_='mm-p-info-cell clearfix').li.span.text
        self._location = soup.find('li', class_='mm-p-cell-right').span.text

    def parse_album_id(self, resp):
        soup = BeautifulSoup(resp, 'lxml')
        pattern = re.compile(r'album_id=(\d+)')

        tags = soup.h4.find_all('a')
        for tag in tags:
            match = pattern.search(tag['href'])
            if match:
                album_id = match.group(1)
                album_name = tag.text.strip().replace('.', '')
                self._albums.append(Album(album_id,
                                          album_name,
                                          self._id,
                                          self._name,
                                          self._location,
                                          session=self._session))

    async def get_info(self):
        user_info_url = user_info.format(self._id)
        resp = await self.fetch(user_info_url)
        self.parse_user_info(resp)

    async def get_albums(self):
        # 获取相册页面数
        pages = await self.get_page_nums()
        # 获取相册列表
        tasks = [self.get_album_by_page(page + 1) for page in range(min(MAX_ALBUM_PAGE, pages) or pages)]
        await asyncio.wait(tasks)

    def __repr__(self):
        return '<User(id={} name={})>'.format(self._id, self._name)


class Manager:
    def __init__(self, loop):
        self._users = []
        self._loop = loop
        self._session = aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=CONCURRENT_LEVEL))

    async def __await__(self):
        await self.get_users()
        print(self)
        await asyncio.wait(self._users)
        await self._session.close()

    async def get_page_nums(self):
        # get users list page nums
        user_list_url = user_list.format(FIRST_PAGE)
        resp = await self.fetch(user_list_url)
        return self.parse_page_nums(resp)

    async def get_user_by_page(self, page):
        user_list_url = user_list.format(page)
        resp = await self.fetch(user_list_url)
        return self.parse_user_id(resp)

    async def get_users(self):
        # 获取用户页面数
        pages = await self.get_page_nums()
        # 获取用户列表
        tasks = [self.get_user_by_page(page + 1) for page in range(min(MAX_USER_PAGE, pages) or pages)]
        done_tasks, _ = await asyncio.wait(tasks)
        for done_task in done_tasks:
            for user_id in done_task.result():
                self._users.append(User(user_id, session=self._session))

    async def fetch(self, url):
        with async_timeout.timeout(TIMEOUT):
            async with self._session.get(url) as response:
                return await response.text()

    @staticmethod
    def parse_page_nums(resp):
        # parse user list ids
        soup = BeautifulSoup(resp, 'lxml')
        pages = int(soup.find('input', id='J_Totalpage').get('value', 0))
        return pages

    @staticmethod
    def parse_user_id(resp):
        soup = BeautifulSoup(resp, 'lxml')
        return (item['data-userid'] for item in soup.find_all('span', class_='friend-follow J_FriendFollow'))

    def __repr__(self):
        return '<Manager(users_num={})>'.format(len(self._users))


if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    with timer():
        manager = Manager(loop)
        loop.run_until_complete(manager)
    loop.close()
