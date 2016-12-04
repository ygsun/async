#!/usr/bin/env python3
"""
Python version: > 2.7
Dependence: gevent greenlet requests BeautifulSoup

gevent协程版本

爬虫类
从淘女郎网站（https://mm.taobao.com）获取图片链接并下载，按照地区、相册名、姓名分类
"""

import gevent
import sys
from gevent import monkey

monkey.patch_all()

import requests

import contextlib
import os
import re
import json
import time

from bs4 import BeautifulSoup

# 第一页
FIRST_PAGE = 1

# 需要抓取的最大用户页数
MAX_USER_PAGE = 2

# 需要抓取的最大相册页数
MAX_ALBUM_PAGE = 2

# 需要抓取的最大照片页数
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
def timer(title='default'):
    start = time.time()
    yield
    print('{}::{:.3f}s'.format(title, time.time() - start))


class Photo(gevent.Greenlet):
    g_count = 0

    def __init__(self, id, url, album_name, user_name, location, session):
        super(Photo, self).__init__()
        self._id = id
        self._url = 'https:' + url
        self._user_name = user_name
        self._album_name = album_name
        self._location = location
        self._session = session
        self._path = os.path.join(os.getcwd(), 'taomm', self._location, self._user_name, self._album_name)
        os.makedirs(self._path, exist_ok=True)

    def _run(self):
        # 获取image内容
        # image = await self.fetch(self._url)
        print(self)
        Photo.g_count += 1

        # 开线程保存到文件
        # await self._session.loop.run_in_executor(None, self.save, image)

    # 异步获取页面内容
    def fetch(self, url):
        return self._session.get(url).text

    def save(self, image):
        path = self._path + '\\' + self._id + '.jpg'
        with open(path, 'wb') as f:
            f.write(image)

    def __repr__(self):
        return '<Photo(id={} url={})>'.format(self._id, self._url)


class Album(gevent.Greenlet):
    def __init__(self, id, name, user_id, user_name, location, *, session):
        super(Album, self).__init__()
        self._id = id
        self._user_id = user_id
        self._name = name
        self._user_name = user_name
        self._location = location
        self._photos = []
        self._session = session

    def _run(self):
        # 异步获取照片列表
        self.get_photos()
        print(self)

        # 等待照片保存任务完成
        gevent.joinall(self._photos)

    def get_page_nums(self):
        # get users list page nums
        photo_list_url = photo_list.format(self._user_id, self._id, FIRST_PAGE)
        resp = self.fetch(photo_list_url)
        return self.parse_page_nums(resp)

    def get_photo_by_page(self, page):
        photo_list_url = photo_list.format(self._user_id, self._id, page)
        resp = self.fetch(photo_list_url)
        return self.parse_photo_url(resp)

    # 异步获取页面内容
    def fetch(self, url):
        return self._session.get(url).text

    @staticmethod
    def parse_page_nums(resp):
        json_data = json.loads(resp)
        pages = int(json_data['totalPage'])
        return pages

    def parse_photo_url(self, resp):
        json_data = json.loads(resp)
        photos = json_data['picList']

        photo_items = []

        for photo in photos:
            photo = Photo(photo['picId'],
                          photo['picUrl'],
                          self._name,
                          self._user_name,
                          self._location,
                          session=self._session)
            photo_items.append(photo)
        return photo_items

    def get_photos(self):
        # 获取照片页面数
        pages = self.get_page_nums()

        # 获取照片列表
        tasks = [gevent.spawn(self.get_photo_by_page, page + 1) for page in range(min(MAX_PHOTO_PAGE, pages))]
        for task in gevent.iwait(tasks):
            photo_objs = task.get()
            for photo in photo_objs:
                photo.start()
                self._photos.append(photo)

    def __repr__(self):
        return '<Album(id={} name={} user={})>'.format(self._id, self._name, self._user_name)


class User(gevent.Greenlet):
    def __init__(self, id, *, session):
        super(User, self).__init__()
        self._id = id
        self._name = ''
        self._location = ''
        self._albums = []
        self._session = session

    def _run(self):
        # 获取用户信息
        self.get_info()
        print(self)

        # 获取相册
        self.get_albums()

        # 等待完成
        gevent.joinall(self._albums)

    def get_page_nums(self):
        # get users list page nums
        album_list_url = album_list.format(self._id, FIRST_PAGE)
        resp = self.fetch(album_list_url)
        return self.parse_page_nums(resp)

    def get_album_by_page(self, page):
        album_list_url = album_list.format(self._id, page)
        resp = self.fetch(album_list_url)
        return self.parse_album_id(resp)

    # 异步获取页面内容
    def fetch(self, url):
        return self._session.get(url).text

    @staticmethod
    def parse_page_nums(resp):
        soup = BeautifulSoup(resp, 'html.parser')
        pages = int(soup.find('input', id='J_Totalpage').get('value', 0))
        return pages

    def parse_user_info(self, resp):
        soup = BeautifulSoup(resp, 'html.parser')
        self._name = soup.find('ul', class_='mm-p-info-cell clearfix').li.span.text
        self._location = soup.find('li', class_='mm-p-cell-right').span.text

    def parse_album_id(self, resp):
        soup = BeautifulSoup(resp, 'html.parser')
        pattern = re.compile(r'album_id=(\d+)')

        album_items = []

        tags = soup.select('h4 a')
        for tag in tags:
            match = pattern.search(tag['href'])
            if match:
                album_id = match.group(1)
                album_name = tag.text.strip().replace('.', '').strip()
                album = Album(album_id,
                              album_name,
                              self._id,
                              self._name,
                              self._location,
                              session=self._session)
                album_items.append(album)
        return album_items

    def get_info(self):
        user_info_url = user_info.format(self._id)
        resp = self.fetch(user_info_url)
        self.parse_user_info(resp)

    def get_albums(self):
        # 获取相册页面数
        pages = self.get_page_nums()

        # 获取相册列表
        tasks = [gevent.spawn(self.get_album_by_page, page + 1) for page in range(min(MAX_ALBUM_PAGE, pages))]
        for task in gevent.iwait(tasks):
            album_objs = task.get()
            for album in album_objs:
                album.start()
                self._albums.append(album)

    def __repr__(self):
        return '<User(id={} name={})>'.format(self._id, self._name)


class Manager(gevent.Greenlet):
    def __init__(self):
        super(Manager, self).__init__()
        self._users = []
        self._session = requests.Session()

    def _run(self):
        # 创建User's Greenlet对象
        with timer('get_users'):
            self.get_users()

        # 等待完成
        with timer('join_users'):
            gevent.joinall(self._users)

        # 关闭session
        self._session.close()

    def get_user_pages(self):
        # 第一页的用户页面URL
        user_list_url = user_list.format(FIRST_PAGE)

        # 异步获取页面内容并返回页数
        resp = self.fetch(user_list_url)
        return self.parse_page_nums(resp)

    def get_user_by_page(self, page):
        # 第N页的用户页面URL
        user_list_url = user_list.format(page)

        # 异步获取页面内容并返回页数
        resp = self.fetch(user_list_url)
        return self.parse_user_id(resp)

    def get_users(self):
        # 获取用户页数
        pages = self.get_user_pages()

        # 获取用户列表
        tasks = [gevent.spawn(self.get_user_by_page, page + 1) for page in range(min(MAX_USER_PAGE, pages))]
        for task in gevent.iwait(tasks):
            user_ids = task.get()
            for user_id in user_ids:
                user = User(user_id, session=self._session)
                user.start()
                self._users.append(user)

    # 异步获取页面内容
    def fetch(self, url):
        return self._session.get(url).text

    @staticmethod
    def parse_page_nums(content):
        soup = BeautifulSoup(content, 'html.parser')
        pages = int(soup.find('input', id='J_Totalpage').get('value', 0))
        return pages

    @staticmethod
    def parse_user_id(content):
        soup = BeautifulSoup(content, 'html.parser')
        return [item['data-userid'] for item in soup.find_all('span', class_='friend-follow J_FriendFollow')]

    def __repr__(self):
        return '<Manager(users_num={})>'.format(len(self._users))


if __name__ == '__main__':
    # 计时
    with timer('main'):
        manager = Manager()
        manager.start()
        gevent.joinall([manager])

    print('{} photos fetched.'.format(Photo.g_count))
