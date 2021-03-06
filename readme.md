## Установка зависимостей
```
pip3 install -r requirements.txt
```

Если Вы используете Windows ниже 10 версии, необходимо дополнительно установить пакет `colorama`:
```
pip3 install colorama
```

## CLI
Есть возможность работы в CLI режиме.

Для сохранения типов данных за один запуск необходимо указывать каждый тип отдельным аргументом `dump`.
Например, для сохранения аудио и видео надо запускать `dump.py --dump audio --dump video`.

## Конфиг модуля vk_api
Поскольку в конфиге хранится `access_token`, получаемый с `offline` правом, позволяющим пройти аутентификацию с любого IP без необходимости ввода кода двухфакторной аутентификации, по умолчанию конфиг будет записываться в память.

Однако, в таком случае, при каждой попытке входа будет запрошен новый код двухфакторой аутентификации, если она включена. Если Вы уверены в безопасности данных, хранимых в конфиге, в настройках можете выключить принудительное сохранение в память.

## Авторизация
Возможны два способа аутентификации - с помощью пары логин-пароль или токена. При использовании токена сохранение аудио будет **невозможно**.

Для входа по токену необходимо передать аргумент `token` при запуске:
```
python3 dump.py --token your_token_here
```

## Многопроцессорная загрузка
Количество процессов, создаваемых при дампе, по умолчанию равняется `4*потоки`.

При загрузке видео - числу, заданному в настройках, но не больше количества потоков.
Такое ограничение введено ввиду отсутствия смысла в спаме лишними процессами при загрузке больших по размеру видео.
Данный лимит может быть отключен в настройках.

## Поддерживаемые для сохранения данные
- [x] Фото
- [x] Аудио
- [x] Видео
- [x] Документы
- [x] Диалоги (txt) и вложения (фото, видео, документы, голосовые)
- [x] Вложения понравившихся постов (фото, видео, документы)
- [ ] прочее, прочее, прочее ;)

## F.A.Q.
**Q: Ошибка vk_api.exceptions.AccessDenied: You don't have permissions to browse user's audio**\
**A:** Попробуйте удалить файл `vk_config.v2.json` и переавторизироваться.

**Q: Ошибка RegexNotFoundError('Unable to extract %s' % _name)**\
**A:** Обновите `youtube_dl`: `pip3 install --upgrade youtube_dl`.
