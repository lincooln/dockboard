import json
import os
import requests
from urllib.parse import urlparse

# Путь к файлу настроек
DATA_DIR = os.environ.get('DATA_DIR', '.')
SETTINGS_FILE = os.path.join(DATA_DIR, 'dashboard_settings.json')

# Файл для хранения настроек
SETTINGS_FILE = 'dashboard_settings.json'

def load_settings():
    """
    Загружает настройки из JSON файла
    """
    if not os.path.exists(SETTINGS_FILE):
        default_settings = {
            'settings_version': '3.0',
            'containers': {},
            'sort_settings': {
                'method': 'name_asc',
                'group_by_status': True
            },
            'ui_settings': {
                'background': '#1a1a1a',
                'card_background': '#2d2d2d',
                'text_color': '#e0e0e0',
                'accent_color': '#4CAF50',
                'border_color': '#404040',
                'border_radius': '8',
                'font_size_base': '14',
                'font_size_large': '16',
                'font_size_small': '12'
            },
            'disk_settings': {
                'show_system': True,
                'show_mounted': True
            },
            'favorites': []
        }
        save_settings(default_settings)
        return default_settings

    try:
        with open(SETTINGS_FILE, 'r', encoding='utf-8') as f:
            settings = json.load(f)

            # Миграция со старой версии
            if settings.get('settings_version', '1.0') != '3.0':
                settings = migrate_to_v3(settings)

            return settings
    except Exception as e:
        print(f"Ошибка загрузки настроек: {e}")
        return get_default_settings()

def get_default_settings():
    """Возвращает настройки по умолчанию"""
    return {
        'settings_version': '3.0',
        'containers': {},
        'sort_settings': {
            'method': 'name_asc',
            'group_by_status': True
        },
        'ui_settings': {
            'background': '#1a1a1a',
            'card_background': '#2d2d2d',
            'text_color': '#e0e0e0',
            'accent_color': '#4CAF50',
            'border_color': '#404040',
            'border_radius': '8',
            'font_size_base': '14',
            'font_size_large': '16',
            'font_size_small': '12'
        },
        'disk_settings': {
            'show_system': True,
            'show_mounted': True
        },
        'favorites': []
    }

def migrate_to_v3(old_settings):
    """Миграция на версию 3.0"""
    print("🔧 Миграция настроек на версию 3.0")

    new_settings = get_default_settings()

    # Переносим старые настройки
    if 'containers' in old_settings:
        new_settings['containers'] = old_settings['containers']

    if 'sort_settings' in old_settings:
        new_settings['sort_settings'] = old_settings['sort_settings']

    if 'ui_settings' in old_settings:
        # Объединяем со значениями по умолчанию
        for key, value in old_settings['ui_settings'].items():
            new_settings['ui_settings'][key] = value

    if 'disk_settings' in old_settings:
        new_settings['disk_settings'] = old_settings['disk_settings']

    if 'favorites' in old_settings:
        # Обновляем иконки для избранного
        new_settings['favorites'] = update_favorite_icons(old_settings['favorites'])

    save_settings(new_settings)
    return new_settings

def save_settings(settings):
    """
    Сохраняет настройки в JSON файл
    """
    try:
        with open(SETTINGS_FILE, 'w', encoding='utf-8') as f:
            json.dump(settings, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"Ошибка сохранения настроек: {e}")
        return False

def initialize_container_settings(container):
    """
    Инициализирует настройки для контейнера
    """
    settings_data = load_settings()

    if 'containers' not in settings_data:
        settings_data['containers'] = {}

    # Используем ID контейнера как ключ
    container_id = container.id

    if container_id not in settings_data['containers']:
        settings_data['containers'][container_id] = {
            'visible': True,
            'custom_name': '',
            'custom_url': '',
            'icon': '🐳'
        }
        save_settings(settings_data)

    return settings_data['containers'][container_id]

def get_container_settings(container_id):
    """
    Возвращает настройки для конкретного контейнера по ID
    """
    settings_data = load_settings()
    return settings_data.get('containers', {}).get(container_id, {})

def update_container_settings(container, new_settings):
    """
    Обновляет настройки для контейнера
    """
    settings = load_settings()

    if 'containers' not in settings:
        settings['containers'] = {}

    container_id = container.id

    if container_id not in settings['containers']:
        settings['containers'][container_id] = {
            'visible': True,
            'custom_name': '',
            'custom_url': '',
            'icon': '🐳'
        }

    # Обновляем только переданные поля
    for key, value in new_settings.items():
        settings['containers'][container_id][key] = value

    return save_settings(settings)

def update_container_settings_by_id(container_id, new_settings):
    """
    Обновляет настройки для контейнера по ID (для остановленных контейнеров)
    """
    settings = load_settings()

    if 'containers' not in settings:
        settings['containers'] = {}

    if container_id not in settings['containers']:
        settings['containers'][container_id] = {
            'visible': True,
            'custom_name': '',
            'custom_url': '',
            'icon': '🐳'
        }

    # Обновляем настройки
    for key, value in new_settings.items():
        settings['containers'][container_id][key] = value

    return save_settings(settings)

def get_hidden_services():
    """
    Возвращает список ID скрытых сервисов
    """
    settings = load_settings()
    hidden_services = []

    for container_id, container_settings in settings.get('containers', {}).items():
        if not container_settings.get('visible', True):
            hidden_services.append(container_id)

    return hidden_services

def hide_service(service_id):
    """
    Скрывает сервис (устанавливает visible=False)
    """
    settings = load_settings()

    if 'containers' not in settings:
        settings['containers'] = {}

    if service_id not in settings['containers']:
        settings['containers'][service_id] = {
            'visible': False,
            'custom_name': '',
            'custom_url': '',
            'icon': '🐳'
        }
    else:
        settings['containers'][service_id]['visible'] = False

    return save_settings(settings)

def get_all_container_settings():
    """
    Возвращает ВСЕ настройки контейнеров
    """
    settings = load_settings()
    return settings.get('containers', {})

def delete_container_settings(container_key):
    """
    Полностью удаляет настройки контейнера
    """
    settings = load_settings()
    if container_key in settings.get('containers', {}):
        del settings['containers'][container_key]
        return save_settings(settings)
    return False

def get_sort_settings():
    """
    Загружает и возвращает текущие настройки сортировки контейнеров.
    Если настроек нет, возвращает значения по умолчанию.
    """
    settings_data = load_settings()

    # Настройки по умолчанию
    default_sort = {
        'method': 'name_asc',
        'group_by_status': True
    }

    # Возвращаем настройки или значения по умолчанию
    sort_settings = settings_data.get('sort_settings', {})

    # Заполняем отсутствующие поля значениями по умолчанию
    for key, value in default_sort.items():
        if key not in sort_settings:
            sort_settings[key] = value

    return sort_settings

def update_sort_settings(new_settings):
    """
    Обновляет настройки сортировки контейнеров, сохраняя их в файл.
    Принимает словарь с новыми настройками.
    """
    settings_data = load_settings()

    if 'sort_settings' not in settings_data:
        settings_data['sort_settings'] = {}

    # Обновляем только переданные поля
    for key, value in new_settings.items():
        settings_data['sort_settings'][key] = value

    return save_settings(settings_data)

def get_ui_settings():
    """
    Загружает и возвращает текущие настройки пользовательского интерфейса.
    Если настроек нет, возвращает значения по умолчанию.
    """
    settings_data = load_settings()

    # Настройки по умолчанию
    default_ui = {
        'background': '#1a1a1a',
        'card_background': '#2d2d2d',
        'text_color': '#e0e0e0',
        'accent_color': '#4CAF50',
        'border_color': '#404040',
        'border_radius': '8',
        'font_size_base': '14',
        'font_size_large': '16',
        'font_size_small': '12'
    }

    # Возвращаем настройки или значения по умолчанию
    ui_settings = settings_data.get('ui_settings', {})

    # Заполняем отсутствующие поля значениями по умолчанию
    for key, value in default_ui.items():
        if key not in ui_settings:
            ui_settings[key] = value

    return ui_settings

def update_ui_settings(new_settings):
    """
    Обновляет настройки пользовательского интерфейса, сохраняя их в файл.
    Принимает словарь с новыми настройками.
    """
    settings_data = load_settings()

    if 'ui_settings' not in settings_data:
        settings_data['ui_settings'] = {}

    # Обновляем только переданные поля
    for key, value in new_settings.items():
        settings_data['ui_settings'][key] = value

    return save_settings(settings_data)

def get_disk_settings():
    """
    Загружает и возвращает текущие настройки отображения дисков.
    Если настроек нет, возвращает значения по умолчанию.
    """
    settings_data = load_settings()

    # Настройки по умолчанию
    default_disk = {
        'show_system': True,
        'show_mounted': True
    }

    # Возвращаем настройки или значения по умолчанию
    disk_settings = settings_data.get('disk_settings', {})

    # Заполняем отсутствующие поля значениями по умолчанию
    for key, value in default_disk.items():
        if key not in disk_settings:
            disk_settings[key] = value

    return disk_settings

def update_disk_settings(new_settings):
    """
    Обновляет настройки отображения дисков, сохраняя их в файл.
    Принимает словарь с новыми настройками.
    """
    settings_data = load_settings()

    if 'disk_settings' not in settings_data:
        settings_data['disk_settings'] = {}

    # Обновляем только переданные поля
    for key, value in new_settings.items():
        settings_data['disk_settings'][key] = value

    return save_settings(settings_data)

def get_favorites():
    """
    Загружает и возвращает список избранных сайтов.
    Добавляет иконку по умолчанию, если она отсутствует.
    """
    settings_data = load_settings()
    favorites = settings_data.get('favorites', [])

    # Убедимся что у каждого есть иконка
    for fav in favorites:
        if 'icon' not in fav:
            fav['icon'] = '🌐'

    return favorites

def update_favorites(new_favorites):
    """
    Обновляет список избранных сайтов, сохраняя его в файл.
    Автоматически обновляет иконки для сайтов.
    """
    settings_data = load_settings()

    # Обновляем иконки перед сохранением
    new_favorites = update_favorite_icons(new_favorites)

    settings_data['favorites'] = new_favorites
    return save_settings(settings_data)

def update_favorite_icons(favorites):
    """
    Обновляет иконки для каждого избранного сайта, пытаясь получить их фавикон.
    """
    for fav in favorites:
        if fav.get('url'):
            fav['icon'] = get_favicon(fav['url'])
        else:
            fav['icon'] = '🌐'
    return favorites

def get_favicon(url):
    """
    Получает фавикон для сайта
    Возвращает иконку или глобус по умолчанию
    """
    try:
        # Парсим URL
        parsed = urlparse(url)
        if not parsed.netloc:
            return '🌐'

        # Пробуем получить фавикон через Google Favicon Service
        favicon_url = f"https://www.google.com/s2/favicons?domain={parsed.netloc}&sz=64"

        try:
            response = requests.get(favicon_url, timeout=2)
            if response.status_code == 200:
                # Если получили фавикон, возвращаем иконку сайта
                return '🌐'  # Можно было бы вернуть URL иконки, но для простоты оставляем эмодзи
        except:
            pass

        # Пробуем прямой доступ к favicon.ico
        favicon_urls = [
            f"http://{parsed.netloc}/favicon.ico",
            f"https://{parsed.netloc}/favicon.ico",
        ]

        for favicon_url in favicon_urls:
            try:
                response = requests.get(favicon_url, timeout=2)
                if response.status_code == 200:
                    return '🌐'
            except:
                continue

        return '🌐'
    except Exception as e:
        print(f"❌ Ошибка получения фавикона для {url}: {e}")
        return '🌐'
