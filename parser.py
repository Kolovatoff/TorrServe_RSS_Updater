import json
import os
import sys
import xml.dom.minidom
from datetime import datetime

import requests


class TorrServerRSSUpdater:

    def run(self):
        # Torrserver
        hosts = [
            'http://192.168.1.83:8090'
        ]
        # Адрес RSS. Можно использовать RSS для чтения, чтобы подгрузить постеры напрямую из RSS
        url = 'http://litr.cc/rss/d02e7a69357c64210a8aa8d932e1cd64'

        # для загрузки постеров на imgur
        imgur_token = ''
        rss_text = requests.get(url).text
        print('Дата отправки запроса ' + str(datetime.now()))
        print('')

        otkaz = False
        path_old_rss = os.path.basename(sys.argv[0]) + '_old.rss'
        try:
            old_rss = open(path_old_rss, 'r').read()
            if rss_text == old_rss:
                print('Без изменений. Пропущено')
                print('Для перезапуска удалите файл ' + path_old_rss)
                otkaz = True
        except:
            ()

        if otkaz:
            exit()

        my_file = open(path_old_rss, 'w')
        my_file.write(rss_text)
        my_file.close()

        for host in hosts:
            print('-------------------------------------------')
            print(host)
            print('-------------------------------------------')
            json_list = []
            json1 = {
                'action': 'list'
            }
            try:
                response = requests.post(host + '/torrents', '', json1, timeout=10)
                # 200 - значит всё ОК
                json_list = json.loads(response.text)
            except requests.exceptions.RequestException as e:
                print('Ошибка подключения к хосту ' + host)
                continue

            doc = xml.dom.minidom.parseString(rss_text)
            torrents = doc.getElementsByTagName('item')
            torrents_added = []
            for torrent in torrents:

                torrent_title = ''
                torrent_link = ''
                torrent_poster = ''
                torrent_guid = ''
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
                    desription_block = torrent.getElementsByTagName('description')
                    if len(desription_block) > 0 and len(desription_block[0].childNodes) > 0:
                        block_text = desription_block[0].childNodes[0].data
                        img_tag = 'img src="'
                        start_img = block_text.find(img_tag)
                        if start_img > 0:
                            end_img = block_text.find('" alt="', start_img)
                            torrent_poster = block_text[start_img + len(img_tag):end_img]
                        start_link = block_text.find('magnet:')
                        if start_link > 0:
                            end_link = block_text.find('&', start_link)
                            torrent_link = block_text[start_link:end_link]
                ind_symbol = torrent_guid.rfind('#', 1);
                if ind_symbol >= 0:
                    torrent_guid = torrent_guid[0:ind_symbol]

                if len(imgur_token) > 0 and len(torrent_poster) > 0:
                    api = 'https://api.imgur.com/3/image'

                    params = dict(
                        client_id=imgur_token
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
                    response = requests.post(host + '/torrents', '', json1, timeout=10)
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
                    response = requests.post(host + '/torrents', '', json1, timeout=10)
                    # 200 - значит всё ОК
                    if response.status_code == 200:
                        print('Новый торрент добавлен')
                    else:
                        continue
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                # Ищем старые торрренты, ищем просмотренные серии и удаляем
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
                    response = requests.post(host + '/viewed', '', json1, timeout=10)
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
                        response = requests.post(host + '/viewed', '', json1, timeout=10)
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
                    response = requests.post(host + '/torrents', '', json1, timeout=10)
                    # 200 - значит всё ОК
                    if response.status_code == 200:
                        print('Старый торрент удален')
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                print('')


if __name__ == '__main__':
    torr_server_rss_updater = TorrServerRSSUpdater()
    torr_server_rss_updater.run()
