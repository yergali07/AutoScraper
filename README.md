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

Дважды кликни `start.bat` — откроется консоль с логами.

## Автозапуск при включении ПК (Task Scheduler)

Чтобы скрипт запускался автоматически при загрузке Windows (даже без входа в систему):

1. Открой **Task Scheduler** (Win + R → `taskschd.msc`)
2. Нажми **Create Task...** (не Basic Task)
3. Вкладка **General**:
   - Имя: `KBTU AutoScraper`
   - Выбери **Run whether user is logged on or not**
   - Поставь галочку **Run with highest privileges**
4. Вкладка **Triggers** → **New...**:
   - Begin the task: **At startup**
5. Вкладка **Actions** → **New...**:
   - Program: `C:\путь\к\репозиторию\AutoScraper\venv\Scripts\python.exe`
   - Arguments: `open_kbtu.py`
   - Start in: `C:\путь\к\репозиторию\AutoScraper`
6. Нажми **OK**, введи пароль Windows

Скрипт будет запускаться при каждом включении ПК — без WSL, без Docker, без входа в систему.

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