import socket
import docker
import settings

def get_host_ip():
    """
    Определяет IP адрес сервера для доступа из сети
    """
    try:
        # Создаем временное соединение чтобы определить внешний IP
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            # Подключаемся к публичному DNS (не отправляем данные)
            s.connect(("8.8.8.8", 80))
            host_ip = s.getsockname()[0]
            return host_ip
    except Exception:
        # Если не получилось, возвращаем localhost как запасной вариант
        return "127.0.0.1"

def get_services():
    """
    Основная функция для получения списка Docker-сервисов для главной страницы
    """
    try:
        client = docker.from_env()
        host_ip = get_host_ip()

        # Получаем ВСЕ контейнеры (включая остановленные)
        all_containers = client.containers.list(all=True)

        services = []

        for container in all_containers:
            service_info = analyze_container(container, host_ip)
            if service_info:
                # Проверяем настройки видимости
                container_settings = settings.get_container_settings(container.id)
                is_visible = container_settings.get('visible', True)

                if is_visible:
                    services.append(service_info)

        # СОРТИРУЕМ сервисы согласно настройкам
        sorted_services = sort_services(services)

        print(f"🎯 Для главной страницы: {len(sorted_services)} сервисов")
        return sorted_services

    except Exception as e:
        print(f"❌ Ошибка при подключении к Docker: {e}")
        return []

def get_web_ports(container):
    """
    Извлекает проброшенные порты из контейнера
    """
    ports = []

    try:
        # Смотрим на настройки сети контейнера
        network_settings = container.attrs['NetworkSettings']['Ports'] or {}

        for container_port, host_ports in network_settings.items():
            if host_ports:  # Если порт проброшен на хост
                for host_mapping in host_ports:
                    host_port = host_mapping['HostPort']
                    # Берем порты в разумном диапазоне для веб-сервисов
                    if host_port.isdigit() and 80 <= int(host_port) <= 9999:
                        ports.append(int(host_port))

        return sorted(ports)  # Сортируем по возрастанию

    except Exception as e:
        print(f"⚠️ Ошибка получения портов для {container.name}: {e}")
        return []

def get_display_name(container):
    """
    Определяет красивое имя для отображения
    """
    labels = container.labels

    # Сначала проверяем кастомные лейблы
    if 'dashboard.name' in labels:
        return labels['dashboard.name']

    # Пытаемся получить имя из compose проекта
    compose_project = labels.get('com.docker.compose.project')
    compose_service = labels.get('com.docker.compose.service')

    if compose_project and compose_service:
        # Для compose: используем только имя сервиса, если оно не стандартное
        if compose_service in ['web', 'app', 'server']:
            return compose_project
        else:
            return compose_service

    # Используем имя контейнера
    return container.name

def get_all_services_for_settings():
    """
    Возвращает все сервисы для страницы настроек с сортировкой
    Только существующие контейнеры (без удаленных)
    """
    try:
        client = docker.from_env()
        host_ip = get_host_ip()

        # Получаем ВСЕ контейнеры (включая остановленные)
        all_containers = client.containers.list(all=True)

        services = []

        for container in all_containers:
            service_info = analyze_container(container, host_ip)
            if service_info:
                services.append(service_info)

        # СОРТИРУЕМ согласно настройкам
        sorted_services = sort_services(services)

        print(f"⚙️ Для страницы настроек: {len(sorted_services)} сервисов")
        return sorted_services

    except Exception as e:
        print(f"❌ Ошибка при получении сервисов для настроек: {e}")
        return []

def analyze_container(container, host_ip):
    """
    Анализирует контейнер с учетом настроек
    """
    try:
        ports = get_web_ports(container)

        # Получаем текущие настройки для контейнера
        container_settings = settings.get_container_settings(container.id)

        # Если настроек нет, инициализируем их
        if not container_settings:
            container_settings = settings.initialize_container_settings(container)

        # Используем кастомное имя если задано, иначе автоматическое
        if container_settings.get('custom_name'):
            display_name = container_settings['custom_name']
        else:
            display_name = get_display_name(container)

        # Определяем URL для отображения и для перехода
        auto_url = ""
        if ports:
            main_port = ports[0]
            auto_url = f"http://{host_ip}:{main_port}"

        custom_url = container_settings.get('custom_url', '')

        # URL для перехода: кастомный если есть, иначе автоматический
        service_url = custom_url if custom_url else auto_url

        # Используем иконку из настроек
        icon = container_settings.get('icon', '🐳')

        return {
            'id': container.id,
            'name': display_name,
            'url': service_url,  # URL для перехода
            'auto_url': auto_url,  # Автоматический URL для отображения
            'custom_url': custom_url,  # Кастомный URL для отображения
            'icon': icon,
            'ports': ports,
            'status': container.status,
            'image': container.image.tags[0] if container.image.tags else 'unknown',
            'visible': container_settings.get('visible', True),
            'container_name': container.name,
            'has_custom_url': bool(custom_url)  # Флаг что есть кастомный URL
        }
    except Exception as e:
        print(f"⚠️ Ошибка анализа контейнера {container.name}: {e}")
        return None

def sort_services(services):
    """Сортирует сервисы согласно настройкам"""
    sort_settings = settings.get_sort_settings()
    method = sort_settings.get('method', 'name_asc')
    group_by_status = sort_settings.get('group_by_status', True)

    print(f"🔧 Сортировка: метод={method}, группировка_по_статусу={group_by_status}")

    if method == 'name_desc':
        return sort_by_name_desc(services, group_by_status)
    elif method == 'ports_asc':
        return sort_by_ports_asc(services, group_by_status)
    elif method == 'ports_desc':
        return sort_by_ports_desc(services, group_by_status)
    else:  # name_asc по умолчанию
        return sort_by_name_asc(services, group_by_status)

def sort_by_name_asc(services, group_by_status):
    """Сортировка по имени (А-Я)"""
    if group_by_status:
        running = [s for s in services if s.get('status') == 'running']
        stopped = [s for s in services if s.get('status') != 'running']

        running_sorted = sorted(running, key=lambda x: x['name'].lower())
        stopped_sorted = sorted(stopped, key=lambda x: x['name'].lower())

        return running_sorted + stopped_sorted
    else:
        return sorted(services, key=lambda x: x['name'].lower())

def sort_by_name_desc(services, group_by_status):
    """Сортировка по имени (Я-А)"""
    if group_by_status:
        running = [s for s in services if s.get('status') == 'running']
        stopped = [s for s in services if s.get('status') != 'running']

        running_sorted = sorted(running, key=lambda x: x['name'].lower(), reverse=True)
        stopped_sorted = sorted(stopped, key=lambda x: x['name'].lower(), reverse=True)

        return running_sorted + stopped_sorted
    else:
        return sorted(services, key=lambda x: x['name'].lower(), reverse=True)

def sort_by_ports_asc(services, group_by_status):
    """Сортировка по портам (возрастание)"""
    def get_max_port(service):
        ports = service.get('ports', [])
        return max(ports) if ports else 0

    if group_by_status:
        running = [s for s in services if s.get('status') == 'running']
        stopped = [s for s in services if s.get('status') != 'running']

        running_sorted = sorted(running, key=get_max_port)
        stopped_sorted = sorted(stopped, key=get_max_port)

        return running_sorted + stopped_sorted
    else:
        return sorted(services, key=get_max_port)

def sort_by_ports_desc(services, group_by_status):
    """Сортировка по портам (убывание)"""
    def get_max_port(service):
        ports = service.get('ports', [])
        return max(ports) if ports else 0

    if group_by_status:
        running = [s for s in services if s.get('status') == 'running']
        stopped = [s for s in services if s.get('status') != 'running']

        running_sorted = sorted(running, key=get_max_port, reverse=True)
        stopped_sorted = sorted(stopped, key=get_max_port, reverse=True)

        return running_sorted + stopped_sorted
    else:
        return sorted(services, key=get_max_port, reverse=True)
