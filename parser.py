import json
import os
import sys
import toml
import codecs
import xml.dom.minidom
from datetime import datetime

import requests


class TorrServerRSSUpdater:

    _config = dict
    _rss_update = str
    _rss_old = str

    def __init__(self, config='config.toml'):
        self._config = toml.load(config)

    def check_updates(self):
        print('Дата отправки запроса {}'.format(str(datetime.now())))

        self._rss_update = requests.get(self._config.get('litr').get('url')).text
        path_old_rss = os.path.basename(sys.argv[0]) + '_old.rss'
        try:
            self._rss_old = open(path_old_rss, 'r', encoding="utf-8").read()
            if self._rss_update == self._rss_old:
                print('Без изменений. Пропущено')
                print('Для перезапуска удалите файл {}'.format(path_old_rss))
                return False
        except OSError:
            my_file = codecs.open(path_old_rss, 'w', 'utf-8')
            my_file.write(self._rss_update)
            my_file.close()
            return True

    def run(self):

        if self.check_updates():
            self.process_torrserver()

    def process_torrserver(self):
        for torrserver in self._config.get('torrservers'):
            print('-------------------------------------------\n'
                  'Сервер: {}\n'
                  '-------------------------------------------'.format(torrserver['host']))
            json_list = []
            json1 = {
                'action': 'list'
            }
            try:
                response = requests.post(torrserver['host'] + '/torrents', '', json1, timeout=10)
                # 200 - значит всё ОК
                json_list = json.loads(response.text)
            except requests.exceptions.RequestException as e:
                print('Ошибка подключения к хосту: {}'.format(torrserver['host']))
                continue

            doc = xml.dom.minidom.parseString(self._rss_update)
            torrents = doc.getElementsByTagName('item')
            torrents_added = []
            for torrent in torrents:

                torrent_title = torrent_link = torrent_poster = torrent_guid = ''
                for childTitle in torrent.getElementsByTagName('title'):
                    for childName in childTitle.childNodes:
                        torrent_title = childName.data
                for childLink in torrent.getElementsByTagName('link'):
                    for childName in childLink.childNodes:
                        torrent_link = childName.data
                for childGuid in torrent.getElementsByTagName('guid'):
                    for childName in childGuid.childNodes:
                        torrent_guid = childName.data

                if (len(torrent_link) == 0) or (torrent_link[0:4] == 'http'):
                    # значит это RSS для чтения, находим магнет ссылку и постер в html содержимом
                    description_block = torrent.getElementsByTagName('description')
                    if len(description_block) > 0 and len(description_block[0].childNodes) > 0:
                        block_text = description_block[0].childNodes[0].data
                        img_tag = 'img src="'
                        start_img = block_text.find(img_tag)
                        if start_img > 0:
                            end_img = block_text.find('" alt="', start_img)
                            torrent_poster = block_text[start_img + len(img_tag):end_img]
                        start_link = block_text.find('magnet:')
                        if start_link > 0:
                            end_link = block_text.find('&', start_link)
                            torrent_link = block_text[start_link:end_link]
                ind_symbol = torrent_guid.rfind('#', 1)
                if ind_symbol >= 0:
                    torrent_guid = torrent_guid[0:ind_symbol]

                if len(self._config.get('imgur_token').get('token')) > 0 and len(torrent_poster) > 0:
                    api = 'https://api.imgur.com/3/image'

                    params = dict(
                        client_id=self._config.get('imgur_token').get('token')
                    )

                    files123 = dict(
                        image=(None, torrent_poster),
                        name=(None, ''),
                        type=(None, 'URL'),
                    )
                    r_imgur = requests.post(api, files=files123, params=params)
                    if r_imgur.status_code == 200:
                        try:
                            torrent_poster = r_imgur.json()['data']['link']
                        except requests.exceptions.RequestException as e:
                            print(e)

                print(torrent_title)
                print(torrent_link)
                print(torrent_guid)
                print(torrent_poster)

                # Проверяем добавляли ли торрент с таким хэшем ранее, если да, то ничего не делаем
                torrent_hash = torrent_link.replace('magnet:?xt=urn:btih:', '')
                json1 = {
                    'action': 'get',
                    'hash': torrent_hash
                }
                try:
                    response = requests.post(torrserver['host'] + '/torrents', '', json1, timeout=10)
                    # 200 - значит торрент уже добавлен
                    if response.status_code == 200:
                        print('Уже добавлен')
                        print('')
                        continue
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                # Добавляем новый торрент
                json1 = {
                    'action': 'add',
                    'link': torrent_link,
                    'title': torrent_title,
                    'poster': torrent_poster,
                    'save_to_db': True,
                    'data': torrent_guid
                }
                try:
                    response = requests.post(torrserver['host'] + '/torrents', '', json1, timeout=10)
                    # 200 - значит всё ОК
                    if response.status_code == 200:
                        print('Новый торрент добавлен')
                    else:
                        continue
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                # Ищем старые торренты, ищем просмотренные серии и удаляем
                search_limit = 100
                old_hash = ''
                current_torrent = 0
                for old_torrent in json_list:
                    current_torrent += 1
                    if current_torrent > search_limit:
                        break
                    if 'data' not in old_torrent or 'hash' not in old_torrent:
                        continue
                    if old_torrent['data'] == torrent_guid and old_torrent['hash'] != torrent_hash:
                        old_hash = old_torrent['hash']
                        break

                if old_hash == '':
                    # старый хэш не нашли
                    print('')
                    continue

                # запоминаем просмотренные серии из старого торрента
                viewed_list = []
                json1 = {
                    'action': 'list',
                    'hash': old_hash
                }
                try:
                    response = requests.post(torrserver['host'] + '/viewed', '', json1, timeout=10)
                    # 200 - значит всё ОК
                    viewed_list = json.loads(response.text)
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                set_viewed_complete = False
                for viewed_index in viewed_list:
                    json1 = {
                        'action': 'set',
                        'hash': torrent_hash,
                        'file_index': viewed_index['file_index']
                    }
                    try:
                        response = requests.post(torrserver['host'] + '/viewed', '', json1, timeout=10)
                        # 200 - значит всё ОК
                        if response.status_code == 200:
                            set_viewed_complete = True
                            continue
                    except requests.exceptions.RequestException as e:
                        print('Ошибка подключения')
                        continue
                if set_viewed_complete:
                    print('Просмотренные серии загружены')

                json1 = {
                    'action': 'rem',
                    'hash': old_hash
                }
                try:
                    response = requests.post(torrserver['host'] + '/torrents', '', json1, timeout=10)
                    # 200 - значит всё ОК
                    if response.status_code == 200:
                        print('Старый торрент удален')
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue


if __name__ == '__main__':
    torr_server_rss_updater = TorrServerRSSUpdater()
    torr_server_rss_updater.run()
