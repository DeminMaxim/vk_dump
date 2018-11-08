#!/usr/bin/env python3
# -*- coding: utf-8 -*-

# Imports
import argparse
from configparser import ConfigParser

from os import get_terminal_size, makedirs, walk, name as osname, sched_getaffinity as os_sched_getaffinity
from os.path import exists, join as pjoin
from sys import stdout
from time import sleep

from urllib.request import urlopen
import requests
import shutil
from re import search as research

import itertools
from multiprocessing import Pool
from multiprocessing.pool import MaybeEncodingError

import vk_api
from youtube_dl import YoutubeDL


NAME = 'VK Dump Tool'
VERSION = '0.6'
API_VERSION = '5.87'

parser = argparse.ArgumentParser(description=NAME)
parser.add_argument('--token', type=str, dest='TOKEN',
                    help='access_token for auth')

AVAILABLE_THREADS = len(os_sched_getaffinity(0))

settings = {
    'REPLACE_SPACES': False,  # заменять пробелы на _
    'REPLACE_CHAR': '_',  # символ для замены запрещённых в Windows символов,
    'POOL_PROCESSES': 4*AVAILABLE_THREADS,
    'LIMIT_VIDEO_PROCESSES': True
}

settings_names = {
    'REPLACE_SPACES': 'Заменять пробелы на символ "_"',
    'REPLACE_CHAR': 'Символ для замены запрещённых в имени файла',
    'POOL_PROCESSES': 'Количество процессов для мультипоточной загрузке',
    'LIMIT_VIDEO_PROCESSES': 'Ограничивать число процессов при загрузке видео'
}

INVALID_CHARS = ['\\', '/', ':', '*', '?', '<', '>', '|', '"']
INVALID_POSIX_CHARS = ['$']

# Dump funcs


def init():
    global parser, args, w, h, colors, mods, settings, INVALID_CHARS

    args = parser.parse_args()

    if osname == 'posix':
        INVALID_CHARS += INVALID_POSIX_CHARS

    config = ConfigParser()
    if not config.read('settings.ini'):
        with open('settings.ini', 'w') as cf:
            config['SETTINGS'] = settings
            config.write(cf)
    else:
        for s in config['SETTINGS']:
            c = config['SETTINGS'][s]
            try:
                settings[s.upper()] = int(c)
            except ValueError:
                settings[s.upper()] = True if c == 'True' else \
                    False if c == 'False' else \
                    c

    w, h = get_terminal_size()
    colors = {
        'red': '\x1b[31m',
        'green': '\x1b[32m',
        'yellow': '\x1b[33m',
        'blue': '\x1b[34m',
        'purple': '\x1b[35m',
        'cyan': '\x1b[36m',
        'white': '\x1b[37m',
    }
    mods = {
        'nrm': '\x1b[0m',
        'bold': '\x1b[1m'
    }
    makedirs('dump', exist_ok=True)


def settings_save():
    global settings

    config = ConfigParser()
    with open('settings.ini', 'w') as cf:
        config['SETTINGS'] = settings
        config.write(cf)


def log(*msg):
    clear()
    global login, vk_session, vk, vk_tools, account
    cprint(msg[0] if msg else '[для продолжения необходимо войти]',
           color='red', mod='bold', offset=2, delay=1/50)
    try:
        if args.TOKEN:
            vk_session = vk_api.VkApi(token=args.TOKEN, app_id=6631721,
                                      auth_handler=auth_handler, api_version=API_VERSION)
        else:
            login = input('    login: \x1b[1;36m')
            print('\x1b[0m', end='')
            password = input('    password: \x1b[1;36m')
            print('\x1b[0m', end='')
            vk_session = vk_api.VkApi(login, password, app_id=6631721,
                                      auth_handler=auth_handler, api_version=API_VERSION)
            vk_session.auth(token_only=True, reauth=True)
        vk = vk_session.get_api()
        vk_tools = vk_api.VkTools(vk)
        account = vk.account.getProfileInfo()
    except KeyboardInterrupt:
        goodbye()
    except vk_api.exceptions.ApiError:
        log('Произошла ошибка при попытке авторизации.')
    except vk_api.exceptions.BadPassword:
        log('Неправильный пароль.')
    except vk_api.exceptions.Captcha:
        log('Необходим ввод капчи.')
    except Exception:
        raise e


def auth_handler():
    key = input('Введите код двухфакторой аутентификации: ')
    remember_device = True
    return key, remember_device


def download(obj, folder, **kwargs):
    if not obj:
        pass

    if isinstance(obj, str):
        url = obj
        del obj
    elif isinstance(obj, dict):
        url = obj.pop('url')
        kwargs = obj

    if 'name' in kwargs:
        fn = '_'.join(kwargs['name'].split(' ')) if settings['REPLACE_SPACES'] else kwargs['name']
        if 'ext' in kwargs:
            if fn.split('.')[-1] != kwargs['ext']:
                fn += '.{}'.format(kwargs['ext'])
    else:
        fn = url.split('/')[-1]

    if 'prefix' in kwargs:
        fn = str(kwargs['prefix']) + '_' + fn

    if 'access_key' in kwargs:
        url = '{}?access_key={ak}'.format(url, ak=kwargs['access_key'])

    for c in INVALID_CHARS:
        fn = fn.replace(c, settings['REPLACE_CHAR'])

    if not exists(pjoin(folder, fn)):
        try:
            r = requests.get(url, stream=True, timeout=(30, 5))
            with open(pjoin(folder, fn), 'wb') as f:
                shutil.copyfileobj(r.raw, f)
                # for chunk in r.iter_content(chunk_size=1024):
                #     if chunk:
                #         f.write(chunk)
        except requests.exceptions.ConnectionError:
            pass
        except requests.exceptions.ReadTimeout:
            pass
        except Exception as e:
            raise e


def download_video(v, folder):
    from pprint import pprint
    if 'platform' in v:
        if v['platform'] == 'YouTube':
            download_youtube(v['player'], folder)
    else:
        if not 'player' in v:
            None
        if 'height' not in v:
            v['height'] = 480 if 'photo_800' in v else \
                360 if 'photo_320' in v else \
                240

        url = v['player'] if not 'access_key' in v else '{}?access_key={ak}'.format(
            v['player'], at=v['access_key'])
        data = urlopen(v['player']).read()
        try:
            download(
                research(b'https://cs.*vkuservideo.*' +
                         str(min(v['height'], v['width'])).encode()+b'.mp4', data).group(0).decode(),
                folder,
                # во избежание конфликта имён к имени файла добавляется его ID
                name=v['title']+'_'+str(v['id']),
                ext='mp4'
            )

        except AttributeError:
            pass


def download_youtube(url, folder):
    if not url:
        pass

    YoutubeDL({
        'outtmpl': pjoin(folder, '%(title)s_%(id)s.%(ext)s'),
        'nooverwrites': True,
        'no_warnings': True,
        'quiet': True
    }).download((url,))


def dump_photos():
    makedirs(pjoin('dump', 'photos'), exist_ok=True)
    albums = vk.photos.getAlbums(need_system=1)

    print('Сохранение фото:')

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = pjoin('dump', 'photos', '_'.join(al['title'].split(' ')))
        makedirs(folder, exist_ok=True)

        photos = vk_tools.get_all(
            method='photos.get',
            max_count=1000,
            values={
                'album_id': al['id'],
                'photo_sizes': 1
            })

        if photos['count'] == 0:
            print('    0/0')
        else:
            objs = []
            for p in photos['items']:
                objs.append(p['sizes'][-1]['url'])

            print('    .../{}'.format(photos['count']), end='\r')
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(objs, itertools.repeat(folder)))
            print('\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), photos['count']))


def dump_audio():
    global folder
    import vk_api.audio

    print('[получение списка аудио]')
    tracks = vk_api.audio.VkAudio(vk_session).get()

    folder = pjoin('dump', 'audio')
    makedirs(folder, exist_ok=True)

    print('\nСохранение аудио:')

    if len(tracks) == 0:
        print('  0/0')
    else:
        audios = []
        for a in tracks:
            audios.append({
                'url': a['url'],
                # во избежание конфликта имён к имени файла добавляется его ID
                'name': '{artist} - {title}_{id}'.format(artist=a['artist'], title=a['title'], id=a['id']),
                'ext': 'mp3'
            })

        print('  .../{}'.format(len(tracks)), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(audios, itertools.repeat(folder)))
        print('\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), len(tracks)))


def dump_video():
    folder = pjoin('dump', 'video')
    makedirs(folder, exist_ok=True)

    print('Сохранение видео:')

    albums = vk_tools.get_all(
        method='video.getAlbums',
        max_count=100,
        values={
            'need_system': 1
        })

    for al in albums['items']:
        print('  Альбом "{}":'.format(al['title']))
        folder = pjoin('dump', 'video', '_'.join(al['title'].split(' ')))
        makedirs(folder, exist_ok=True)

        video = vk_tools.get_all(
            method='video.get',
            max_count=200,
            values={
                'album_id': al['id']
            })

        if video['count'] == 0:
            print('    0/0')
        else:
            objs = []
            for v in video['items']:
                objs.append(v)

            print('    .../{}'.format(video['count']), end='\r')
            with Pool(settings['POOL_PROCESSES'] if not settings['LIMIT_VIDEO_PROCESSES'] else AVAILABLE_THREADS) as pool:
                pool.starmap(download_video, zip(objs, itertools.repeat(folder)))
            print('\x1b[2K    {}/{}'.format(len(next(walk(folder))[2]), video['count']))


def dump_docs():
    folder = pjoin('dump', 'docs')
    makedirs(folder, exist_ok=True)

    print('[получение списка документов]')

    docs = vk.docs.get()

    print('Сохраненние документов:')

    if docs['count'] == 0:
        print('  0/0')
    else:
        objs = []
        for d in docs['items']:
            objs.append({
                'url': d['url'],
                # во избежание конфликта имён к имени файла добавляется его ID
                'name': d['title']+'_'+str(d['id']),
                'ext': d['ext']
            })

        print('  .../{}'.format(docs['count']), end='\r')
        with Pool(settings['POOL_PROCESSES']) as pool:
            pool.starmap(download, zip(objs, itertools.repeat(folder)))
        print('\x1b[2K  {}/{}'.format(len(next(walk(folder))[2]), docs['count']))


def dump_messages():
    def users_add(id):
        try:
            if id > 0:
                # Users: {..., first_name, last_name, id, ...} => {%id%: {name: 'first_name + last_name', length: len(name) }
                u = vk.users.get(user_ids=id)[0]
                if ('deactivated' in u) and (u['deactivated'] == 'deleted') and (u['first_name'] == 'DELETED'):
                    name = 'DELETED'
                    users[u['id']] = {'name': name, 'length': len(name)}
                else:
                    name = u['first_name'] + ' ' + u['last_name']
                    users[u['id']] = {'name': name, 'length': len(name)}

            elif id < 0:
                # Groups: {..., name, id, ...} => {-%id%: {name: 'name', length: len(name) }
                g = vk.messages.getConversationsById(peer_ids=id, extended=1)['groups'][0]
                name = g['name']
                users[-g['id']] = {'name': name, 'length': len(name)}

        except Exception:
            users[id] = {'name': r'{unknown user}', 'length': 3}

    def message_handler(msg):
        """
            Обработчик сообщений.
            Возвращает массив строк.

            [документация API]
                [вложения]
                    [сообщения]
                        - vk.com/dev/objects/attachments_m
                    [wall_reply]
                        - vk.com/dev/objects/attachments_w
        """
        r = []

        if ('fwd_messages' in msg) and msg['fwd_messages']:
            for fwd in msg['fwd_messages']:
                res = message_handler(fwd)
                if len(res) > 0:
                    if fwd['from_id'] not in users:
                        users_add(fwd['from_id'])

                    r.append('{name}> {}'.format(res[0], name=users.get(fwd['from_id'])['name']))
                    for m in res[1:]:
                        r.append('{name}> {}'.format(
                            m, name=' '*len(users.get(fwd['from_id'])['name'])))

        if len(msg['text']) > 0:
            for line in msg['text'].split('\n'):
                r.append(line)

        if msg['attachments']:
            for at in msg['attachments']:
                tp = at['type']
                if tp == 'photo':
                    if 'action' not in msg:
                        r.append('[фото: {url}]'.format(url=at[tp]['sizes'][-1]['url']))
                elif tp == 'video':
                    r.append(
                        '[видео: vk.com/video{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                elif tp == 'audio':
                    r.append('[аудио: {artist} - {title}]'.format(artist=at[tp]
                                                                  ['artist'], title=at[tp]['title']))
                elif tp == 'doc':
                    r.append(
                        '[документ: vk.com/doc{owid}_{id}]'.format(owid=at[tp]['owner_id'], id=at[tp]['id']))
                elif tp == 'link':
                    r.append('[ссылка: {title} ({url})]'.format(
                        title=at[tp]['title'], url=at[tp]['url']))
                elif tp == 'market':
                    r.append('[товар: {title} ({price}{cur}) [vk.com/market?w=product{owid}_{id}]]'.format(
                        title=at[tp]['title'],
                        owid=at[tp]['owner_id'],
                        id=at[tp]['id'],
                        price=at[tp]['price']['amount'],
                        cur=at[tp]['price']['currency']['name'].lower()))
                # TODO: доделать market_album
                elif tp == 'market_album':
                    r.append('[коллекция товаров: {title}]'.format(title=at[tp]['title']))
                elif tp == 'wall':
                    r.append(
                        '[пост: vk.com/wall{owid}_{id}]'.format(owid=at[tp]['to_id'], id=at[tp]['id']))
                # TODO: доделать wall_reply: добавить поддержку вложений (а надо ли?)
                elif tp == 'wall_reply':
                    if at[tp]['from_id'] not in users:
                        users_add(at[tp]['from_id'])
                    u = users.get(at[tp]['from_id'])
                    r.append('[комментарий к посту от {user}: {text} (vk.com/wall{owid}_{pid}?reply={id})]'.format(
                        user=u['name'],
                        text=at[tp]['text'],
                        owid=at[tp]['owner_id'],
                        pid=at[tp]['post_id'],
                        id=at[tp]['id']))
                elif tp == 'sticker':
                    r.append('[стикер: {url}]'.format(url=at[tp]['images'][-1]['url']))
                elif tp == 'gift':
                    r.append('[подарок: {id}]'.format(id=at[tp]['id']))
                elif tp == 'graffiti':
                    r.append('[граффити: {url}]'.format(url=at[tp]['url']))
                elif tp == 'audio_message':
                    r.append('[голосовое сообщение: {url}]'.format(url=at[tp]['link_mp3']))
                else:
                    r.append('[вложение с типом "{tp}"]'.format(tp=tp))

        if 'action' in msg and msg['action']:
            """
                member - совершающий действие
                user - объект действия
            """
            act = msg['action']
            tp = act['type']

            if ('member_id' in act) and (act['member_id'] > 0) and (act['member_id'] not in users):
                try:
                    users_add(act['member_id'])
                except Exception:
                    users[act['member_id']] = {'name': r'{unknown user}', 'length': 3}

            if tp == 'chat_photo_update':
                r.append('[{member} обновил фотографию беседы ({url})]'.format(
                    member=users[msg['from_id']]['name'],
                    url=msg['attachments'][0]['photo']['sizes'][-1]['url']
                ))
            elif tp == 'chat_photo_remove':
                r.append('[{member} удалил фотографию беседы]'.format(
                    member=users[msg['from_id']]['name']
                ))
            elif tp == 'chat_create':
                r.append('[{member} создал чат "{chat_name}"]'.format(
                    member=users[msg['from_id']]['name'],
                    chat_name=act['text']
                ))
            elif tp == 'chat_title_update':
                r.append('[{member} изменил название беседы на «{chat_name}»]'.format(
                    member=users[msg['from_id']]['name'],
                    chat_name=act['text']
                ))
            elif tp == 'chat_invite_user':
                r.append('[{member} пригласил {user}]'.format(
                    member=users[msg['from_id']]['name'],
                    user=users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
                ))
            elif tp == 'chat_kick_user':
                r.append('[{member} исключил {user}]'.format(
                    member=users[msg['from_id']]['name'],
                    user=users[act['member_id']]['name'] if act['member_id'] > 0 else act['email'],
                ))
            elif tp == 'chat_pin_message':
                r.append('[{member} закрепил сообщение #{id}: "{message}"]'.format(
                    member=users[msg['from_id']]['name'],
                    id=act['conversation_message_id'],
                    message=act['message'] if 'message' in act else ''
                ))
            elif tp == 'chat_unpin_message':
                r.append('[{member} открепил сообщение]'.format(
                    member=users[msg['from_id']]['name']
                ))
            elif tp == 'chat_invite_user_by_link':
                r.append('[{user} присоединился по ссылке]'.format(
                    user=users[msg['from_id']]['name']
                ))

        return r

    folder = pjoin('dump', 'dialogs')
    makedirs(folder, exist_ok=True)

    # get conversations
    print('[получение диалогов...]')
    print('\x1b[2K  0/???', end='\r')

    conversations = vk_tools.get_all(
        method='messages.getConversations',
        max_count=200,
        values={
            'extended': 1,
            'fields': 'first_name, last_name, name'
        })

    print('\x1b[2K  {}/{}'.format(len(conversations['items']), conversations['count']))

    users = {}

    print('Сохранение диалогов:')
    for con in conversations['items']:
        did = con['conversation']['peer']['id']

        if con['conversation']['peer']['type'] == 'user':
            if did not in users:
                users_add(did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'group':
            if did not in users:
                users_add(did)
            dialog_name = users.get(did)['name']
        elif con['conversation']['peer']['type'] == 'chat':
            dialog_name = con['conversation']['chat_settings']['title']
        else:
            dialog_name = r'{unknown}'

        print('  Диалог: {}'.format(dialog_name))
        print('    [кэширование]')
        print('\x1b[2K      0/???', end='\r')

        history = vk_tools.get_all(
            method='messages.getHistory',
            max_count=200,
            values={
                'peer_id': con['conversation']['peer']['id'],
                'rev': 1,
                'extended': 1,
                'fields': 'first_name, last_name'
            })
        print('\x1b[2K      {}/{}'.format(len(history['items']), history['count']))

        # write history to .txt file
        for c in INVALID_CHARS:
            dialog_name = dialog_name.replace(c, settings['REPLACE_CHAR'])

        with open(pjoin('dump', 'dialogs', '{}_{id}.txt'.format('_'.join(dialog_name.split(' ')), id=did)), 'w', encoding='utf-8') as f:
            count = len(history['items'])
            print('    [сохранение]')
            print('\x1b[2K      {}/{}'.format(0, count), end='\r')
            prev = None
            for i in range(count):
                m = history['items'][i]

                if m['from_id'] not in users:
                    users_add(m['from_id'])

                hold = ' '*(users.get(m['from_id'])['length']+2)
                msg = hold if (prev and prev == m['from_id']) else users.get(
                    m['from_id'])['name']+': '

                res = message_handler(m)
                if res:
                    msg += res[0] + '\n'
                    for r in res[1:]:
                        msg += hold + r + '\n'
                else:
                    msg += '\n'

                f.write(msg)
                prev = m['from_id']
                print('\x1b[2K      {}/{}'.format(i+1, count), end='\r')
        print()
        print()


def dump_liked_posts(**kwargs):
    folder_photos = pjoin('dump', 'photos', 'Понравившиеся')
    makedirs(folder_photos, exist_ok=True)
    folder_videos = pjoin('dump', 'video', 'Понравившиеся')
    makedirs(folder_videos, exist_ok=True)
    folder_docs = pjoin('dump', 'docs', 'Понравившиеся')
    makedirs(folder_docs, exist_ok=True)

    print('[получение постов]')

    posts = vk.execute.posts(basic_offset=0)
    i = 0
    for i in range(posts[0]//1000):
        res = vk.execute.posts(basic_offset=(i+1)*1000)
        posts[1].extend(res[1])
        del res

    filtered_posts = []
    for i in range(len(posts[1])):
        for p in posts[1][i]:
            filtered_posts.append(p)
    posts = filtered_posts
    del filtered_posts

    photos = []
    video_ids = []
    videos = []
    docs = []

    for p in posts:
        if 'attachments' in p:
            for at in p['attachments']:
                if at['type'] == 'photo':
                    obj = {
                        'url': at['photo']['sizes'][-1]['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id'])}
                    if 'access_key' in at['photo']:
                        obj.update({'access_key': at['photo']['access_key']})
                    photos.append(obj)
                elif at['type'] == 'video':
                    video_ids.append('{oid}_{id}{access_key}'.format(
                        oid=at['video']['owner_id'],
                        id=at['video']['id'],
                        access_key='_' +
                        at['video']['access_key'] if 'access_key' in at['video'] else ''
                    ))
                elif at['type'] == 'doc':
                    obj = {
                        'url': at['doc']['url'],
                        'prefix': '{}_{}'.format(p['owner_id'], p['id']),
                        'name': at['doc']['title'] + '_' + str(at['doc']['id']),
                        'ext': at['doc']['ext']}
                    if 'access_key' in at['doc']:
                        obj.update({'access_key': at['doc']['access_key']})
                    docs.append(obj)

    if video_ids:
        videos = vk_tools.get_all(
            method='video.get',
            max_count=200,
            values={
                'videos': ','.join(video_ids),
                'extended': 1
            }
        )

    print('Сохранение ({} вложений из {} постов):'.format(
        sum([len(photos), len(videos), len(docs)]), len(posts)))

    try:
        if photos:
            print('  [фото ({})]'.format(len(photos)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(photos, itertools.repeat(folder_photos)))
    except MaybeEncodingError:
        None

    try:
        if videos:
            print('  [видео ({}/{})]'.format(len(videos['items']), len(video_ids)))
            with Pool(settings['POOL_PROCESSES'] if not settings['LIMIT_VIDEO_PROCESSES'] else AVAILABLE_THREADS) as pool:
                pool.starmap(download_video, zip(videos['items'], itertools.repeat(folder_videos)))
    except MaybeEncodingError:
        None

    try:
        if docs:
            print('  [документы ({})]'.format(len(docs)))
            with Pool(settings['POOL_PROCESSES']) as pool:
                pool.starmap(download, zip(docs, itertools.repeat(folder_docs)))
    except MaybeEncodingError:
        None


# GUI funcs

def clear(): return print('\x1b[2J', '\x1b[1;1H', end='', flush=True)


def lprint(*args, **kwargs):
    print('\x1b[?25l')
    for s in args:
        if (s.find('\x1b') == -1) and ('slow' in kwargs) and (kwargs['slow']):
            for ch in s:
                stdout.write(ch)
                stdout.flush()
                sleep(kwargs['delay'] if 'delay' in kwargs else 1/50)
        else:
            print(s, end='')
    print('\x1b[?25h')


def cprint(msg, **kwargs):
    if isinstance(msg, list):
        for i in range(len(msg)):
            kwargs['color'][i] = colors[kwargs['color'][i]] if (
                'color' in kwargs and kwargs['color'][i]) else mods['nrm']
            if 'mod' in kwargs and kwargs['mod'][i]:
                kwargs['color'][i] += mods[kwargs['mod'][i]]
            lprint(kwargs['color'][i]+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg[i])/2),
                                                             y=int(h/2-len(msg)/2+i)+1),
                   msg[i], mods['nrm'], **kwargs)

    else:
        if not 'offset' in kwargs:
            kwargs['offset'] = 0
        kwargs['color'] = colors[kwargs['color']] if 'color' in kwargs else mods['nrm']
        if 'mod' in kwargs:
            kwargs['color'] += mods[kwargs['mod']]

        lprint(kwargs['color']+'\x1b[{y};{x}H'.format(x=int(w/2-len(msg)/2),
                                                      y=int(h/2-(len(msg.split('\n'))/2)+1-kwargs['offset'])),
               msg, mods['nrm'], **kwargs)


def welcome():
    clear()
    cprint([NAME, 'v'+VERSION],
           color=['green', None],
           mod=['bold', None],
           slow=True, delay=1/50)

    print('\x1b[?25l')
    sleep(2)
    print('\x1b[?25h')


def goodbye():
    clear()
    cprint(['Спасибо за использование скрипта :з', '', 'Made with ♥ by hikiko4ern'],
           color=['green', None, 'red'], mod=['bold', None, 'bold'])
    raise SystemExit


def logInfo():
    global account, args

    log_info = [
        'Login: \x1b[1;36m{}\x1b[0m'.format(account['phone'] if args.TOKEN else login),
        'Name: \x1b[1;36m{fn} {ln}\x1b[0m'.format(fn=account['first_name'], ln=account['last_name'])
    ]
    ln = 0
    for l in log_info:
        ln = max(len(l), ln)

    print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')
    for l in log_info:
        print('\x1b[31m>\x1b[0m '+l)
    print('\x1b[1;31m'+'-'*(ln-7), end='\x1b[0m\n')


def menu():
    global args

    clear()
    logInfo()
    print()

    actions = [
        'Фото (по альбомам)', dump_photos,
        'Аудио', dump_audio,
        'Видео (по альбомам)', dump_video,
        'Документы', dump_docs,
        'Сообщения', dump_messages,
        'Данные понравившихся постов', dump_liked_posts
    ]

    if args.TOKEN:
        actions.pop(actions.index(dump_audio)-1)
        actions.pop(actions.index(dump_audio))

    print('Дамп данных:\n')

    for i in range(int(len(actions)/2)):
        print('\x1b[34m[{ind}]\x1b[0m {name}'.format(ind=i+1, name=actions[i*2]))
    print('\n\x1b[34m[F]\x1b[0m Все данные')
    print('\n\x1b[34m[S]\x1b[0m Настройки')
    print('\x1b[34m[Q]\x1b[0m Выход')

    print()
    try:
        choice = input('> ').lower()

        if isinstance(choice, str):
            if choice == 'q':
                choice = exit
            elif choice == 's':
                choice = settings_screen
            elif choice == 'f':
                choice = [actions[i] for i in range(len(actions)) if i % 2 == 1]
            else:
                if int(choice) not in range(1, len(actions)+1):
                    raise IndexError
                choice = actions[(int(choice)-1)*2+1]

        if choice is exit:
            goodbye()
        elif isinstance(choice, list):
            for c in choice:
                c()
                print()
            menu()
        elif callable(choice):
            choice()
            if choice is not settings_screen:
                print('\n\x1b[32mСохранение завершено :з\x1b[0m')
                input('\n[нажмите {clr}Enter{nrm} для продолжения]'.format(
                    clr=colors['cyan']+mods['bold'], nrm=mods['nrm']))
            menu()
        else:
            raise IndexError
    except IndexError:
        cprint('Выберите действие из доступных', color='red', mode='bold')
        sleep(2)
        clear()
        menu()
    except ValueError:
        menu()
    except KeyboardInterrupt:
        goodbye()


def settings_screen():
    clear()
    logInfo()
    print()
    print('Настройки:\n')

    i = 0
    for s in settings:
        value = settings[s]

        if isinstance(value, bool):
            color = colors['green'] if value else colors['red']
            value = 'Да' if value else 'Нет'

        print('\x1b[34m[{ind}]\x1b[0m {name}: {clr}{value}{nrm}'.format(
            ind=i+1,
            name=settings_names[s],
            value=value,
            clr=color if 'color' in locals() else colors['yellow'],
            nrm=mods['nrm']
        ))
        i += 1

        if 'color' in locals():
            del color

    print('\n\x1b[34m[0]\x1b[0m В меню')

    try:
        choice = int(input('> '))
        if choice == 0:
            menu()
        elif choice not in range(1, len(settings)+1):
            raise IndexError()
        else:
            s = [s for s in settings][choice-1]
            new = None
            if isinstance(settings[s], bool):
                settings[s] = not settings[s]
            else:
                while (type(new) is not type(settings[s])) or (s == 'REPLACE_CHAR' and new in INVALID_CHARS):
                    try:
                        new = input('\nВведите новое значение для {clr}{}{nrm} ({tclr}{type}{nrm})\n> '.format(
                            s,
                            clr=colors['red'],
                            tclr=colors['yellow'],
                            nrm=mods['nrm'],
                            type=type(settings[s])))
                        if not new:
                            new = settings[s]
                            break
                        if isinstance(settings[s], int):
                            new = int(new)
                    except ValueError:
                        continue
                settings[s] = new
            settings_save()

        settings_screen()
    except IndexError:
        cprint('Выберите одну из доступных настроек', color='red', mode='bold')
        sleep(2)
        clear()
        settings_screen()
    except ValueError:
        settings_screen()
    except KeyboardInterrupt:
        goodbye()


if __name__ == '__main__':
    stdout.write('\x1b]0;{}\x07'.format(NAME))
    init()
    welcome()
    log()
    menu()
