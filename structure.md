docker-dashboard/
├── .dockerignore          # Игнорируемые файлы для Docker
├── app.py                 # Главный файл приложения
├── build-and-push.sh      # Скрипт для сборки и пуша Docker образа
├── dashboard_settings.json # Настройки панели управления
├── docker_discovery.py    # Обнаружение Docker-сервисов
├── docker-compose.dev.yml # Docker Compose для разработки
├── docker-compose.yml     # Docker Compose для продакшна
├── Dockerfile             # Dockerfile для сборки образа
├── get-docker.sh          # Скрипт для установки Docker
├── README.md              # Описание проекта
├── requirements.txt       # Зависимости Python
├── settings.py            # Управление настройками
├── structure.md           # Структура проекта (этот файл)
├── system_stats.py        # Скрипт для сбора системной статистики
├── TODO.md                # Список задач
├── static/                # Статические файлы
│   ├── dashboard.css      # Стили панели управления
│   ├── favicon.ico        # Иконка сайта
│   └── style.css          # Основные стили
└── templates/             # HTML шаблоны
    ├── appearance.html    # Шаблон настроек внешнего вида
    ├── details.html       # Шаблон деталей сервиса
    ├── favorites.html     # Шаблон избранных сервисов
    ├── index.html         # Главный HTML шаблон
    └── settings.html      # Шаблон общих настроек

Для тестирования и запуска используйте Docker:
# Сборка и запуск контейнера с помощью Docker Compose
docker-compose up --build



