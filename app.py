from flask import Flask, render_template, jsonify, request
import docker_discovery
import settings
import docker
import docker.errors
import system_stats
from datetime import datetime
import os
import re

# Конфигурация путей
DATA_DIR = os.environ.get('DATA_DIR', '.')
os.makedirs(DATA_DIR, exist_ok=True)
app = Flask(__name__)

# Вспомогательные функции для форматирования данных
def format_memory(memory_data):
    """
    Форматирует данные о памяти в читаемый вид.
    Принимает словарь с данными о памяти (использовано, всего, процент).
    Возвращает строку вида "XX.X% (YY.YG/ZZ.ZG)" или "N/A" / "Ошибка".
    """
    if not memory_data or 'used' not in memory_data:
        return "N/A"

    try:
        used_gb = memory_data.get('used', 0) / (1024 ** 3)
        total_gb = memory_data.get('total', 0) / (1024 ** 3)
        percent = memory_data.get('percent', 0)
        return f"{percent:.1f}% ({used_gb:.1f}G/{total_gb:.1f}G)"
    except (TypeError, KeyError):
        return "Ошибка"


# Функция для умного обрезания путей монтирования
def shorten_mount_path_full(full_path, font_size=None):
    # Базовый порог обрезки зависит от размера шрифта
    if font_size is None:
        # По умолчанию используем базовый размер шрифта
        import settings
        ui_settings = settings.get_ui_settings()
        font_size = int(ui_settings.get('font_size_base', 14))
    
    # Рассчитываем порог обрезки на основе размера шрифта
    # При самом большом шрифте (18) порог 16 символов, при меньшем шрифте порог увеличивается
    # Используем базовый порог 16 при font_size 14, и корректируем в зависимости от размера
    threshold = max(10, 30 - (font_size - 12))  # при font_size 18 порог будет 16 (30 - (18-12) = 24), при font_size 12 порог будет 18 (30 - 0 = 30)
    
    # Более точная формула: при font_size 18 порог должен быть 16
    # Для этого пересчитаем: если font_size = 18, то threshold = 16
    # threshold = 34 - font_size (при font_size=18, threshold=16; при font_size=12, threshold=22)
    threshold = max(10, 34 - font_size)
    
    if len(full_path) <= threshold:
        return full_path

    parts = [part for part in full_path.split('/') if part]

    if len(parts) <= 2:
        # Для коротких путей типа /mnt/share
        return full_path

    # Для длинных путей показываем начало и конец: /home/.../share
    first_part = parts[0]
    last_part = parts[-1]

    result = f"/{first_part}/.../{last_part}"
    
    # Проверяем, что результат не длиннее оригинала
    if len(result) >= len(full_path):
        return full_path
    
    return result


def prepare_disk_data(disks, show_system_disks=True, show_mounted_disks=True, font_size=None):
    """
    Подготавливает данные о дисках для отображения в шаблоне.
    Фильтрует диски по типу (системные, монтированные) и добавляет форматированные значения
    и CSS-классы для визуального представления.
    """
    formatted_disks = []
    for disk in disks:
        try:
            # Исключаем EFI разделы
            mountpoint = disk.get('mountpoint', '')
            if mountpoint.startswith('/boot/efi'):
                continue

            # Проверяем фильтры
            disk_type = disk.get('type', '').lower()
            is_system = mountpoint in ['/', '/boot']
            is_network = disk_type in ['smb', 'nfs', 'network', 'cifs']

            if not show_system_disks and is_system:
                continue
            if not show_mounted_disks and is_network:
                continue

            formatted_disk = disk.copy()
            # Добавляем сокращенный путь с умной обрезкой
            formatted_disk['short_path'] = shorten_mount_path_full(mountpoint, font_size)

            # Добавляем GB значения для шаблона
            formatted_disk['used_gb'] = disk.get('used', 0) / (1024 ** 3)
            formatted_disk['total_gb'] = disk.get('total', 0) / (1024 ** 3)

            # Добавляем класс для цветового кодирования
            percent = disk.get('percent', 0)
            if percent > 90:
                formatted_disk['css_class'] = 'danger'
            elif percent > 80:
                formatted_disk['css_class'] = 'warning'
            else:
                formatted_disk['css_class'] = ''

            formatted_disks.append(formatted_disk)
        except Exception as e:
            print(f"❌ Ошибка обработки диска {disk.get('mountpoint')}: {e}")
            continue
    return formatted_disks

def normalize_url(url):
    """
    Нормализует URL, добавляя протокол 'http://' если он отсутствует.
    Удаляет лишние пробелы.
    """
    if not url or url.strip() == '':
        return ''

    url = url.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url

    return url

@app.route('/')
def dashboard():
    """
    Главная страница дашборда
    """
    try:
        # Получаем настройки оформления
        ui_settings = settings.get_ui_settings()

        # 1. Получаем все сервисы из Docker
        all_services = docker_discovery.get_services()

        # 2. Получаем список скрытых сервисов
        hidden_services = settings.get_hidden_services()

        # 3. Фильтруем - оставляем только видимые сервисы
        visible_services = [
            service for service in all_services
            if service.get('id') not in hidden_services
        ]

        # 4. Получаем системную статистику
        system_stats_data = system_stats.get_system_stats()
        container_stats_data = system_stats.get_container_stats()

        # 5. Получаем настройки дисков
        disk_settings = settings.get_disk_settings()

        # 6. Получаем отфильтрованные диски
        disks = prepare_disk_data(
            system_stats_data.get('disks', []),
            disk_settings.get('show_system', True),
            disk_settings.get('show_mounted', True),
            int(ui_settings.get('font_size_base', 14))
        )

        # 7. Получаем избранные сайты
        favorites = settings.get_favorites()
        # Добавляем флаг is_url_icon для каждого избранного сайта
        for fav in favorites:
            fav['is_url_icon'] = fav['icon'].startswith('http') if fav.get('icon') else False

        # 8. Форматируем статистику для шаблона
        formatted_stats = {
            'hostname': system_stats_data.get('hostname', 'N/A'),
            'cpu': f"{system_stats_data.get('cpu_percent', 0):.1f}%",
            'memory': format_memory(system_stats_data.get('memory', {})),
            'containers': {
                'total': container_stats_data.get('total', 0),
                'running': container_stats_data.get('running', 0),
                'stopped': container_stats_data.get('stopped', 0)
            },
            'disks': disks,
            'has_disks': len(disks) > 0,
            'local_ips': system_stats_data.get('local_ips', []),
            'update_time': datetime.now().strftime("%H:%M:%S")
        }

        print(f"🎯 Сервисов: всего {len(all_services)}, показано {len(visible_services)}")
        print(f"📊 Дисков для отображения: {len(disks)}")
        print(f"⭐ Избранных сайтов: {len(favorites)}")

        return render_template('index.html',
                             services=visible_services,
                             stats=formatted_stats,
                             favorites=favorites,
                             ui_settings=ui_settings)

    except Exception as e:
        print(f"❌ Ошибка в dashboard(): {e}")
        return render_template('index.html',
                             services=[],
                             stats={
                                 'hostname': 'N/A',
                                 'cpu': '0.0%',
                                 'memory': 'N/A',
                                 'containers': {'total': 0, 'running': 0, 'stopped': 0},
                                 'disks': [],
                                 'has_disks': False,
                                 'local_ips': [],
                                 'update_time': datetime.now().strftime("%H:%M:%S")
                             },
                             favorites=[],
                             ui_settings=settings.get_ui_settings(),
                             error=str(e))

@app.route('/appearance')
def appearance_page():
    """Страница настроек оформления"""
    try:
        ui_settings = settings.get_ui_settings()
        
        # Получаем системную статистику
        system_stats_data = system_stats.get_system_stats()
        container_stats_data = system_stats.get_container_stats()
        
        # Форматируем статистику для шаблона
        formatted_stats = {
            'hostname': system_stats_data.get('hostname', 'N/A'),
            'cpu': f"{system_stats_data.get('cpu_percent', 0):.1f}%",
            'memory': format_memory(system_stats_data.get('memory', {})),
            'containers': {
                'total': container_stats_data.get('total', 0),
                'running': container_stats_data.get('running', 0),
                'stopped': container_stats_data.get('stopped', 0)
            },
            'local_ips': system_stats_data.get('local_ips', []),
            'update_time': datetime.now().strftime("%H:%M:%S")
        }
        
        return render_template('appearance.html',
                             stats=formatted_stats,
                             ui_settings=ui_settings)
    except Exception as e:
        print(f"❌ Ошибка загрузки страницы оформления: {e}")
        return render_template('appearance.html',
                             ui_settings=settings.get_ui_settings(),
                             error=str(e))

@app.route('/favorites')
def favorites_page():
    """Страница настроек избранных сайтов"""
    try:
        favorites = settings.get_favorites()
        # Добавляем флаг is_url_icon для каждого избранного сайта
        for fav in favorites:
            fav['is_url_icon'] = fav['icon'].startswith('http') if fav.get('icon') else False
        ui_settings = settings.get_ui_settings()
        
        # Получаем системную статистику
        system_stats_data = system_stats.get_system_stats()
        container_stats_data = system_stats.get_container_stats()
        
        # Форматируем статистику для шаблона
        formatted_stats = {
            'hostname': system_stats_data.get('hostname', 'N/A'),
            'cpu': f"{system_stats_data.get('cpu_percent', 0):.1f}%",
            'memory': format_memory(system_stats_data.get('memory', {})),
            'containers': {
                'total': container_stats_data.get('total', 0),
                'running': container_stats_data.get('running', 0),
                'stopped': container_stats_data.get('stopped', 0)
            },
            'local_ips': system_stats_data.get('local_ips', []),
            'update_time': datetime.now().strftime("%H:%M:%S")
        }
        
        return render_template('favorites.html',
                              favorites=favorites,
                              stats=formatted_stats,
                              ui_settings=ui_settings)
    except Exception as e:
        print(f"❌ Ошибка загрузки страницы избранных: {e}")
        return render_template('favorites.html',
                              favorites=[],
                              error=str(e))

@app.route('/details')
def details_page():
    """Страница детализации контейнеров"""
    try:
        # Получаем настройки оформления
        ui_settings = settings.get_ui_settings()
        
        # Получаем системную статистику
        system_stats_data = system_stats.get_system_stats()
        container_stats_data = system_stats.get_container_stats()
        
        # Форматируем статистику для шаблона
        formatted_stats = {
            'hostname': system_stats_data.get('hostname', 'N/A'),
            'cpu': f"{system_stats_data.get('cpu_percent', 0):.1f}%",
            'memory': format_memory(system_stats_data.get('memory', {})),
            'containers': {
                'total': container_stats_data.get('total', 0),
                'running': container_stats_data.get('running', 0),
                'stopped': container_stats_data.get('stopped', 0)
            },
            'local_ips': system_stats_data.get('local_ips', []),
            'update_time': datetime.now().strftime("%H:%M:%S")
        }
        
        return render_template('details.html',
                             stats=formatted_stats,
                             ui_settings=ui_settings)
    except Exception as e:
        print(f"❌ Ошибка загрузки страницы детализации: {e}")
        return render_template('details.html',
                             ui_settings=settings.get_ui_settings(),
                             error=str(e))

# API-эндпоинты

@app.route('/api/stats')
def get_stats():
    """
    API для получения общей статистики системы и контейнеров.
    Возвращает данные в формате JSON.
    """
    stats = system_stats.get_system_stats()
    container_stats = system_stats.get_container_stats()

    return jsonify({
        'system': stats,
        'containers': container_stats
    })

@app.route('/api/get_favicon')
def api_get_favicon():
    """
    API для получения URL фавикона по заданному URL сайта.
    Возвращает JSON с favicon_url.
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'status': 'error', 'message': 'URL не указан'}), 400

    favicon_url = settings.get_favicon(url)
    return jsonify({'status': 'ok', 'favicon_url': favicon_url})

@app.route('/api/hide_service', methods=['POST'])
def hide_service():
    """
    API-эндпоинт для скрытия сервиса.
    Принимает service_id в теле запроса JSON.
    """
    data = request.get_json()
    service_id = data.get('service_id')

    if not service_id:
        return jsonify({'status': 'error', 'message': 'Не указан service_id'}), 400

    success = settings.hide_service(service_id)

    if success:
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500

@app.route('/api/services')
def api_services():
    """
    JSON API для получения списка всех обнаруженных Docker-сервисов.
    """
    services = docker_discovery.get_services()
    return jsonify(services)

@app.route('/api/update_settings', methods=['POST'])
def api_update_settings():
    """API для обновления настроек контейнера"""
    data = request.get_json()
    container_id = data.get('container_id')
    setting_key = data.get('key')
    setting_value = data.get('value')

    print(f"🔧 Получены данные: container_id={container_id}, key={setting_key}, value={setting_value}")

    if not all([container_id, setting_key]):
        return jsonify({'status': 'error', 'message': 'Недостаточно данных'}), 400

    try:
        success = settings.update_container_settings_by_id(container_id, {setting_key: setting_value})

        if success:
            print(f"✅ Настройки сохранены для контейнера {container_id}")
            return jsonify({'status': 'ok'})
        else:
            print(f"❌ Ошибка сохранения для контейнера {container_id}")
            return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500

    except Exception as e:
        print(f"❌ Ошибка обновления настроек: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/delete_container_settings', methods=['POST'])
def api_delete_container_settings():
    """
    API для удаления пользовательских настроек конкретного контейнера.
    Принимает container_key в теле запроса JSON.
    """
    data = request.get_json()
    container_key = data.get('container_key')

    if not container_key:
        return jsonify({'status': 'error', 'message': 'Не указан container_key'}), 400

    success = settings.delete_container_settings(container_key)

    if success:
        return jsonify({'status': 'ok'})
    else:
        return jsonify({'status': 'error', 'message': 'Ошибка удаления'}), 500

@app.route('/api/sort_settings')
def api_get_sort_settings():
    """API для получения настроек сортировки"""
    try:
        sort_settings = settings.get_sort_settings()
        return jsonify(sort_settings)
    except Exception as e:
        print(f"❌ Ошибка получения настроек сортировки: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_sort_settings', methods=['POST'])
def api_update_sort_settings():
    """API для обновления настроек сортировки (JSON)"""
    try:
        data = request.get_json()
        print(f"📦 Получены данные: {data}")

        if not data:
            return jsonify({'status': 'error', 'message': 'Нет данных'}), 400

        success = settings.update_sort_settings(data)

        if success:
            print("✅ Настройки сортировки сохранены")
            return jsonify({'status': 'ok'})
        else:
            print("❌ Ошибка сохранения настроек сортировки")
            return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500

    except Exception as e:
        print(f"❌ Ошибка обновления настроек сортировки: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/get_favorites')
def api_get_favorites():
    """
    API для получения списка избранных сайтов.
    Возвращает список избранных сайтов в формате JSON.
    """
    try:
        favorites = settings.get_favorites()
        return jsonify(favorites)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_favorites', methods=['POST'])
def api_update_favorites():
    """API для обновления избранных сайтов"""
    try:
        data = request.get_json()
        favorites = data.get('favorites', [])

        # Фильтруем пустые записи
        favorites = [fav for fav in favorites if fav.get('url', '').strip()]

        # Нормализуем URL
        for fav in favorites:
            fav['url'] = normalize_url(fav.get('url', ''))

        success = settings.update_favorites(favorites)

        if success:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_ui_settings')
def api_get_ui_settings():
    """
    API для получения текущих настроек пользовательского интерфейса.
    Возвращает настройки в формате JSON.
    """
    try:
        ui_settings = settings.get_ui_settings()
        return jsonify(ui_settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/update_ui_settings', methods=['POST'])
def api_update_ui_settings():
    """API для обновления настроек интерфейса"""
    try:
        data = request.get_json()
        success = settings.update_ui_settings(data)

        if success:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/get_disk_settings')
def api_get_disk_settings():
    """
    API для получения текущих настроек отображения дисков.
    Возвращает настройки в формате JSON.
    """
    try:
        disk_settings = settings.get_disk_settings()
        return jsonify(disk_settings)
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/containers/stats')
def api_containers_stats():
    """API для получения статистики контейнеров"""
    try:
        stats = system_stats.get_detailed_container_stats()
        return jsonify(stats)
    except Exception as e:
        print(f"❌ Ошибка получения статистики контейнеров: {e}")
        return jsonify({'error': str(e)}), 500

@app.route('/api/container/<container_id>/start', methods=['POST'])
def api_container_start(container_id):
    """API для запуска контейнера"""
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
        container.start()
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"❌ Ошибка запуска контейнера {container_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/container/<container_id>/stop', methods=['POST'])
def api_container_stop(container_id):
    """API для остановки контейнера"""
    try:
        client = docker.from_env()
        container = client.containers.get(container_id)
        container.stop()
        return jsonify({'status': 'ok'})
    except Exception as e:
        print(f"❌ Ошибка остановки контейнера {container_id}: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/update_disk_settings', methods=['POST'])
def api_update_disk_settings():
    """API для обновления настроек дисков"""
    try:
        data = request.get_json()
        success = settings.update_disk_settings(data)

        if success:
            return jsonify({'status': 'ok'})
        else:
            return jsonify({'status': 'error', 'message': 'Ошибка сохранения'}), 500
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# ==============================
#  Обработчики HTML-форм
# ==============================

@app.route('/save_sort_settings', methods=['POST'])
def handle_save_sort_settings():
    """Обработка сохранения настроек сортировки (HTML форма)"""
    try:
        method = request.form.get('method', 'name_asc')
        group_by_status = request.form.get('group_by_status') == 'on'

        settings.update_sort_settings({
            'method': method,
            'group_by_status': group_by_status
        })

        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message={'type': 'success', 'text': '✅ Настройки сортировки сохранены'})
    except Exception as e:
        print(f"❌ Ошибка сохранения настроек сортировки: {e}")
        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message={'type': 'error', 'text': f'❌ Ошибка: {str(e)}'})

@app.route('/save_container_settings', methods=['POST'])
def handle_save_container_settings():
    """Обработка массового сохранения настроек контейнеров (HTML форма)"""
    try:
        container_ids = request.form.getlist('container_ids')
        updated_count = 0

        for container_id in container_ids:
            container_settings = {}

            # Видимость
            visible_key = f'visible_{container_id}'
            container_settings['visible'] = request.form.get(visible_key) != 'on'

            # Имя
            name_key = f'name_{container_id}'
            custom_name = request.form.get(name_key, '').strip()
            if custom_name:
                container_settings['custom_name'] = custom_name

            # URL
            url_key = f'url_{container_id}'
            custom_url = request.form.get(url_key, '').strip()
            if custom_url:
                container_settings['custom_url'] = normalize_url(custom_url)

            # Иконка
            icon_key = f'icon_{container_id}'
            icon = request.form.get(icon_key, '').strip()
            if icon:
                container_settings['icon'] = icon

            # Сохраняем, если есть изменения
            if container_settings:
                settings.update_container_settings_by_id(container_id, container_settings)
                updated_count += 1

        message = f'✅ Сохранено настроек для {updated_count} контейнеров'
        if updated_count == 0:
            message = 'ℹ️ Изменений не было'

        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message={'type': 'success', 'text': message})

    except Exception as e:
        print(f"❌ Ошибка сохранения настроек контейнеров: {e}")
        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message={'type': 'error', 'text': f'❌ Ошибка: {str(e)}'})

@app.route('/save_ui_settings', methods=['POST'])
def handle_save_ui_settings():
    """Обработка сохранения настроек интерфейса"""
    try:
        ui_settings = {
            'background': request.form.get('background', '#1a1a1a'),
            'card_background': request.form.get('card_background', '#2d2d2d'),
            'text_color': request.form.get('text_color', '#e0e0e0'),
            'accent_color': request.form.get('accent_color', '#4CAF50'),
            'border_color': request.form.get('border_color', '#404040'),
            'border_radius': request.form.get('border_radius', '8'),
            'font_size_base': request.form.get('font_size_base', '14'),
            'font_size_large': request.form.get('font_size_large', '16'),
            'font_size_small': request.form.get('font_size_small', '12')
        }

        success = settings.update_ui_settings(ui_settings)

        if success:
            message = {'type': 'success', 'text': '✅ Настройки интерфейса сохранены'}
        else:
            message = {'type': 'error', 'text': '❌ Ошибка сохранения настроек интерфейса'}

        return render_template('appearance.html',
                             ui_settings=settings.get_ui_settings(),
                             message=message)

    except Exception as e:
        print(f"❌ Ошибка сохранения настроек интерфейса: {e}")
        return render_template('appearance.html',
                             ui_settings=settings.get_ui_settings(),
                             message={'type': 'error', 'text': f'❌ Ошибка: {str(e)}'})

@app.route('/save_disk_settings', methods=['POST'])
def handle_save_disk_settings():
    """Обработка сохранения настроек дисков"""
    try:
        disk_settings = {
            'show_system': request.form.get('show_system') == 'on',
            'show_mounted': request.form.get('show_mounted') == 'on'
        }

        success = settings.update_disk_settings(disk_settings)

        if success:
            message = {'type': 'success', 'text': '✅ Настройки дисков сохранены'}
        else:
            message = {'type': 'error', 'text': '❌ Ошибка сохранения настроек дисков'}

        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message=message)

    except Exception as e:
        print(f"❌ Ошибка сохранения настроек дисков: {e}")
        return render_template('settings.html',
                             services=docker_discovery.get_all_services_for_settings(),
                             sort_settings=settings.get_sort_settings(),
                             disk_settings=settings.get_disk_settings(),
                             message={'type': 'error', 'text': f'❌ Ошибка: {str(e)}'})

@app.route('/save_favorites', methods=['POST'])
def handle_save_favorites():
    """Обработка сохранения избранных сайтов"""
    try:
        # Собираем все избранные сайты из формы
        favorites = []

        # Сначала собираем непустые записи
        for i in range(10):
            name_key = f'fav_name_{i}'
            url_key = f'fav_url_{i}'

            url = request.form.get(url_key, '').strip()
            if url:
                name = request.form.get(name_key, '').strip()
                icon_key = f'fav_icon_{i}'  # Добавлено для получения иконки
                icon = request.form.get(icon_key, '').strip() # Добавлено для получения иконки

                favorites.append({
                    'name': name if name else url,
                    'url': normalize_url(url),
                    'icon': icon if icon else '🌐' # Используем полученную иконку, или глобус по умолчанию
                })

        # Сохраняем
        success = settings.update_favorites(favorites)

        if success:
            message = {'type': 'success', 'text': '✅ Избранные сайты сохранены'}
        else:
            message = {'type': 'error', 'text': '❌ Ошибка сохранения избранных сайтов'}

        # Загружаем обновленный список избранных сайтов, чтобы получить актуальные иконки
        favorites = settings.get_favorites()

        return render_template('favorites.html',
                             favorites=favorites,
                             message=message)

    except Exception as e:
        print(f"❌ Ошибка сохранения избранных сайтов: {e}")
        return render_template('favorites.html',
                             favorites=settings.get_favorites(),
                             message={'type': 'error', 'text': f'❌ Ошибка: {str(e)}'})

@app.route('/delete_favorite/<int:index>')
def handle_delete_favorite(index):
    """
    Обработчик для удаления избранного сайта по его индексу.
    Перенаправляет пользователя обратно на страницу избранных сайтов.
    """
    try:
        favorites = settings.get_favorites()
        ui_settings = settings.get_ui_settings()
        if 0 <= index < len(favorites):
            favorites.pop(index)
            settings.update_favorites(favorites)
            message = {'type': 'success', 'text': '✅ Избранный сайт удален'}
        else:
            message = {'type': 'error', 'text': '❌ Индекс не найден'}

    except Exception as e:
        print(f"❌ Ошибка удаления избранного сайта: {e}")
        message = {'type': 'error', 'text': f'❌ Ошибка удаления: {str(e)}'}

        return render_template('favorites.html',
                             favorites=favorites,
                             ui_settings=ui_settings)
    # return render_template('favorites.html',
    #                      favorites=settings.get_favorites(),
    #                      message=message)

@app.route('/delete_settings/<container_id>')
def handle_delete_settings(container_id):
    """
    Обработчик для удаления пользовательских настроек контейнера.
    Перенаправляет пользователя обратно на страницу настроек.
    """
    try:
        success = settings.delete_container_settings(container_id)

        if success:
            message = {'type': 'success', 'text': '✅ Настройки удалены'}
        else:
            message = {'type': 'error', 'text': '❌ Настройки не найдены'}

    except Exception as e:
        print(f"❌ Ошибка удаления настроек: {e}")
        message = {'type': 'error', 'text': f'❌ Ошибка удаления: {str(e)}'}

    return render_template('settings.html',
                         services=docker_discovery.get_all_services_for_settings(),
                         sort_settings=settings.get_sort_settings(),
                         disk_settings=settings.get_disk_settings(),
                         message=message)

@app.route('/settings')
def settings_page():
    """Страница основных настроек"""
    try:
        ui_settings = settings.get_ui_settings()
        if request.args.get('reset') == '1':
            settings.update_sort_settings({
                'method': 'name_asc',
                'group_by_status': True
            })
            settings.update_disk_settings({
                'show_system': True,
                'show_mounted': True
            })
            message = {'type': 'success', 'text': '✅ Настройки сброшены к умолчаниям'}
        else:
            message = None

        all_services = docker_discovery.get_all_services_for_settings()
        sort_settings = settings.get_sort_settings()
        disk_settings = settings.get_disk_settings()

        # Получаем системную статистику
        system_stats_data = system_stats.get_system_stats()
        container_stats_data = system_stats.get_container_stats()
        
        # Форматируем статистику для шаблона
        formatted_stats = {
            'hostname': system_stats_data.get('hostname', 'N/A'),
            'cpu': f"{system_stats_data.get('cpu_percent', 0):.1f}%",
            'memory': format_memory(system_stats_data.get('memory', {})),
            'containers': {
                'total': container_stats_data.get('total', 0),
                'running': container_stats_data.get('running', 0),
                'stopped': container_stats_data.get('stopped', 0)
            },
            'local_ips': system_stats_data.get('local_ips', []),
            'update_time': datetime.now().strftime("%H:%M:%S")
        }

        return render_template('settings.html',
                             services=all_services,
                             sort_settings=sort_settings,
                             disk_settings=disk_settings,
                             stats=formatted_stats,
                             ui_settings=ui_settings,
                             message=message)

    except Exception as e:
        print(f"❌ Ошибка загрузки страницы настроек: {e}")
        return render_template('settings.html',
                             services=[],
                             sort_settings={'method': 'name_asc', 'group_by_status': True},
                             disk_settings={'show_system': True, 'show_mounted': True},
                             message={'type': 'error', 'text': f'❌ Ошибка загрузки: {str(e)}'})

if __name__ == '__main__':
    # Инициализация и запуск Flask приложения
    import sys
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 5000
    print(f"🚀 Запуск Docker Dashboard на порту {port}...")
    print(f"📊 Дашборд будет доступен по адресу: http://localhost:{port}")
    print(f"⚙️ Страница настроек: http://localhost:{port}/settings")
    print(f"🎨 Настройки оформления: http://localhost:{port}/appearance")
    print(f"⭐ Избранные сайты: http://localhost:{port}/favorites")
    app.run(host='0.0.0.0', port=port, debug=True)
