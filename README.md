# KBTU AutoScraper

Автоматическая отметка посещаемости на портале KBTU Registration Online.

## Установка (Windows)

### 1. Установи Python

Скачай с [python.org](https://www.python.org/downloads/). При установке **обязательно** поставь галочку "Add Python to PATH".

### 2. Запусти установку

Дважды кликни `install.bat`. Он создаст виртуальное окружение, установит зависимости и скачает Chromium.

### 3. Настрой конфигурацию

`.env` — токен Telegram-бота:

```
TELEGRAM_BOT_TOKEN=your_token_here
```

`users.json` — список пользователей:

```json
[
  {
    "username": "student1",
    "password": "password1",
    "telegram_chat_id": "123456789"
  }
]
```

### 4. Запуск

- **С консолью:** дважды кликни `start.bat`
- **Без окна (фоном):** дважды кликни `start_hidden.vbs`

## Автозапуск при включении ПК (Task Scheduler)

Чтобы скрипт запускался автоматически при каждом входе в Windows:

1. Открой **Task Scheduler** (Win + R → `taskschd.msc`)
2. Нажми **Create Basic Task...**
3. Имя: `KBTU AutoScraper`
4. Trigger: **When I log on**
5. Action: **Start a program**
6. Program: `wscript.exe`
7. Arguments: `"C:\путь\к\AutoScraper\start_hidden.vbs"`
8. Поставь галочку **Run with highest privileges**
9. Готово

Теперь скрипт будет запускаться при каждом входе в Windows — без WSL, без Docker.

## Логи

Логи записываются в папку `logs/autoscraper.log` (ротация: макс 5 МБ, хранится 3 файла).

## Как это работает

1. Загружает пользователей из `users.json`
2. Запускает headless Chromium через Playwright
3. Логинится на портал KBTU
4. Каждые 35 секунд проверяет кнопку "Отметиться"
5. Нажимает и отправляет уведомление в Telegram
6. При ошибке — автоматически перезапускается (бесконечно, с нарастающей задержкой до 5 мин)
7. При падении браузера — перезапускает весь процесс