import json
import os
import toml
import codecs
import requests
from datetime import datetime


class TorrServerRSSUpdater:
    __config = dict
    __json_update = str
    __json_old = str
    __toml_string = """
    [[torrservers]]
    host = "http://127.0.0.1:8090"
    
    [litr]
    url = "https://litr.cc/feed/..."
    
    [imgur_token]
    token = ""
    """

    def __init__(self, config='config.toml'):
        if os.path.exists('config.toml'):
            self.__config = toml.load(config)
        else:
            parsed_toml = toml.loads(self.__toml_string)
            with open('config.toml', 'w') as f:
                toml.dump(parsed_toml, f)
            print('Создан файл конфигурации config.toml')
            print('Отредактируйте файл конфигурации config.toml и запустите программу снова')
            exit()

    def check_updates(self):
        print('Дата отправки запроса {}'.format(str(datetime.now())))

        self.__json_update = requests.get(self.__config.get('litr').get('url')).text
        if os.path.exists('old.tmp'):
            try:
                self.__json_old = open('old.tmp', 'r', encoding="utf-8").read()
                if self.__json_update == self.__json_old:
                    print('Без изменений. Пропущено')
                    print('Для перезапуска удалите файл {}'.format('old.tmp'))
                    return False
                else:
                    my_file = codecs.open('old.tmp', 'w', 'utf-8')
                    my_file.write(self.__json_update)
                    my_file.close()
                    return True
            except OSError:
                raise "Ошибка чтения файла старого запроса"
        else:
            my_file = codecs.open('old.tmp', 'w', 'utf-8')
            my_file.write(self.__json_update)
            my_file.close()
            return True

    def process_torrserver(self):
        for torrserver in self.__config.get('torrservers'):
            print('-------------------------------------------\n'
                  f"Сервер: {torrserver['host']}\n"
                  '-------------------------------------------')
            json_list = []
            try:
                response = requests.post(
                    torrserver['host'] + '/torrents',
                    json={
                        'action': 'list'
                    },
                    timeout=10
                )
                # 200 - значит всё ОК
                json_list = json.loads(response.text)
            except requests.exceptions.RequestException as e:
                print('Ошибка подключения к хосту: {}'.format(torrserver['host']))
                continue

            torrents = json.loads(self.__json_update)['items']
            torrents_added = []
            for torrent in torrents:

                # torrent_title = torrent_link = torrent_poster = torrent_guid = ''
                torrent_title = torrent.get('title', '')
                torrent_link = torrent.get('url', '')
                torrent_hash = torrent.get('id', '').lower()
                torrent_poster = torrent.get('image', '')

                # получение guid из litr
                litr_read = json.loads(requests.get(self.__config.get('litr').get('url') + '/read').text)
                torrent_guid = ''
                for item in litr_read['items']:
                    if item['title'] == torrent_title:
                        torrent_guid = item['id']

                if len(self.__config.get('imgur_token').get('token')) > 0 and len(torrent_poster) > 0:
                    api = 'https://api.imgur.com/3/image'

                    params = dict(
                        client_id=self.__config.get('imgur_token').get('token')
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
                print("torrent_guid: {}".format(torrent_guid))
                print(torrent_poster)

                # Проверяем добавляли ли торрент с таким хэшем ранее, если да, то ничего не делаем
                try:
                    response = requests.post(
                        torrserver['host'] + '/torrents',
                        json={
                            'action': 'get',
                            'hash': torrent_hash
                        },
                        timeout=10
                    )
                    # 200 - значит торрент уже добавлен
                    if response.status_code == 200:
                        print('Уже добавлен')
                        print('')
                        continue
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                # Добавляем новый торрент
                try:
                    response = requests.post(
                        torrserver['host'] + '/torrents',
                        json={
                            'action': 'add',
                            'link': torrent_link,
                            'title': torrent_title,
                            'poster': torrent_poster,
                            'save_to_db': True,
                            'data': json.dumps({'torrent_guid': torrent_guid})
                        },
                        timeout=10
                    )
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
                    if torrent_hash == torrent_guid or torrent_guid == '':
                        break
                    current_torrent += 1
                    if current_torrent > search_limit:
                        break
                    if not 'data' in old_torrent or not 'hash' in old_torrent:
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
                try:
                    response = requests.post(
                        torrserver['host'] + '/viewed',
                        json={
                            'action': 'list',
                            'hash': old_hash
                        },
                        timeout=10
                    )
                    # 200 - значит всё ОК
                    viewed_list = json.loads(response.text)
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

                set_viewed_complete = False
                for viewed_index in viewed_list:
                    try:
                        response = requests.post(
                            torrserver['host'] + '/viewed',
                            json={
                                'action': 'set',
                                'hash': torrent_hash,
                                'file_index': viewed_index['file_index']
                            },
                            timeout=10
                        )
                        # 200 - значит всё ОК
                        if response.status_code == 200:
                            set_viewed_complete = True
                            continue
                    except requests.exceptions.RequestException as e:
                        print('Ошибка подключения')
                        continue
                if set_viewed_complete:
                    print('Просмотренные серии загружены')

                try:
                    response = requests.post(
                        torrserver['host'] + '/torrents',
                        json={
                            'action': 'rem',
                            'hash': old_hash
                        },
                        timeout=10
                    )
                    # 200 - значит всё ОК
                    if response.status_code == 200:
                        print('Старый торрент удален')
                except requests.exceptions.RequestException as e:
                    print('Ошибка подключения')
                    continue

    def run(self):

        if self.check_updates():
            self.process_torrserver()


if __name__ == '__main__':
    torr_server_rss_updater = TorrServerRSSUpdater()
    torr_server_rss_updater.run()
