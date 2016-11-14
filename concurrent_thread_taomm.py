import contextlib
import threading
import queue
import os
import re
import requests
import time

from bs4 import BeautifulSoup

# 淘女郎列表页面
mm_list_page = 'https://mm.taobao.com/json/request_top_list.htm?page={}'

# 淘女郎信息页
mm_index_page = 'https://mm.taobao.com/self/info/model_info_show.htm?user_id={}'

# 淘女郎相册列表页面
mm_album_list_page = 'https://mm.taobao.com/self/album/open_album_list.htm?user_id={}&page={}'

# 淘女郎相册json
mm_album_page = 'https://mm.taobao.com/album/json/get_album_photo_list.htm?user_id={}&album_id={}&page={}'

# 保存路径
pic_path = r'c:\vv'

g_c = 0


class TaoMM(threading.Thread):
    def __init__(self, user_id):
        super(TaoMM, self).__init__()

        # mm id
        self.user_id = user_id

        # mm loc
        self.location = ''

        # mm name
        self.name = ''

        # id <=> alnum_name
        self.albums = {}

    def get_info_by_id(self):
        try:
            resp = requests.get(mm_index_page.format(self.user_id))
            soup = BeautifulSoup(resp.text, 'lxml')
        except:
            pass
        else:
            self.name = soup.find('ul', class_='mm-p-info-cell clearfix').li.span.text
            self.location = soup.find('li', class_='mm-p-cell-right').span.text

    def get_album_pages(self):
        try:
            resp = requests.get(mm_album_list_page.format(self.user_id, 1))
            soup = BeautifulSoup(resp.text, 'lxml')
        except:
            pages = -1
        else:
            pages = int(soup.find('input', id='J_Totalpage')['value'])

        return pages

    def get_photo_pages(self, album_id):
        try:
            resp = requests.get(mm_album_page.format(self.user_id, album_id, 1))
            album_json = resp.json()
        except:
            pages = -1
        else:
            pages = int(album_json['totalPage'])

        return pages

    def get_album_by_page(self, page):
        try:
            resp = requests.get(mm_album_list_page.format(self.user_id, page))
            soup = BeautifulSoup(resp.text, 'lxml')
        except:
            pass
        else:
            pattern = re.compile(r'album_id=(\d+)')
            tags = soup.find_all('a')
            for tag in tags:
                match = pattern.search(tag['href'])
                if match:
                    album_id = match.group(1)
                    self.albums[album_id] = tag.text.strip().replace('.', '')

    @staticmethod
    def save(pic_url, path):
        url = 'https:' + pic_url
        resp = requests.get(url)
        with open(path, 'wb') as f:
            f.write(resp.content)

    def get_photo_by_page(self, album_id, page):
        try:
            resp = requests.get(mm_album_page.format(self.user_id, album_id, page))
            album_json = resp.json()
        except:
            pass
        else:
            photos = len(album_json['picList'])
            return photos
            # for item in album_json['picList']:
            #     print(item['picUrl'])
            # path = self.create_dirs(album_id)
            # for item in album_json['picList']:
            #     self.save(item['picUrl'], path + '\\' + item['picId'] + '.jpg')

    def create_dirs(self, album_id):
        path = os.path.join(pic_path, self.location, self.name, self.albums[album_id])
        os.makedirs(path, exist_ok=True)
        return path

    def run(self):

        self.get_info_by_id()
        album_pages = self.get_album_pages()
        for album_page in range(1):
            self.get_album_by_page(album_page + 1)
            for album_id in self.albums:
                count = 0
                photo_pages = self.get_photo_pages(album_id)
                for photo_page in range(1):
                    photo_size = self.get_photo_by_page(album_id, photo_page + 1)
                    count += photo_size
                    global g_c
                    g_c += photo_size
                print('{} at {} has {} of {} photos'.format(self.name, self.location, self.albums[album_id], count))


def get_mm_count():
    try:
        resp = requests.get(mm_list_page.format(1))
        soup = BeautifulSoup(resp.text, 'lxml')
        count = int(soup.find('input', id='J_Totalpage').get('value', -1))
    except:
        count = -1

    return count


def get_mm_id(page):
    ids = []
    try:
        resp = requests.get(mm_list_page.format(page))
        soup = BeautifulSoup(resp.text, 'lxml')

        for item in soup.find_all('span', class_='friend-follow J_FriendFollow'):
            id = item.get('data-userid')
            if id:
                ids.append(id)
    except:
        pass

    return ids


@contextlib.contextmanager
def timer():
    start = time.time()
    yield
    print('run in {:.1f} seconds'.format(time.time() - start))


if __name__ == '__main__':
    threads = []
    for index in range(1):
        ids = get_mm_id(index + 1)
        for mm_id in ids:
            mm = TaoMM(mm_id)
            mm.start()
            threads.append(mm)

    with timer():
        for th in threads:
            th.join()

    print('All {} photos fetched'.format(g_c))
