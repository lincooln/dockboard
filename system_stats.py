import os
import psutil
import docker
import socket
import subprocess

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

def get_system_stats():
    """
    Получает статистику системы
    """
    try:
        # Hostname
        hostname = os.uname().nodename

        # Локальные IP адреса - используем проверенную функцию
        local_ips = get_local_ip_addresses()

        # Загрузка CPU
        cpu_percent = psutil.cpu_percent(interval=1)

        # Память
        memory = psutil.virtual_memory()
        memory_info = {
            'total': memory.total,
            'used': memory.used,
            'percent': memory.percent
        }

        # Диски
        disk_info = get_disk_info()

        # Температура CPU
        cpu_temp = get_cpu_temperature('/sys')

        return {
            'hostname': hostname,
            'local_ips': local_ips,
            'cpu_temp': cpu_temp,
            'cpu_percent': cpu_percent,
            'memory': memory_info,
            'disks': disk_info,
            'success': True
        }

    except Exception as e:
        print(f"❌ Ошибка получения статистики: {e}")
        return {'success': False, 'error': str(e)}

def get_cpu_temperature(sys_path):
    """Получает температуру CPU с несколькими fallback'ами"""
    possible_paths = [
        f'{sys_path}/class/thermal/thermal_zone0/temp',  # Стандартный путь
        f'{sys_path}/class/hwmon/hwmon0/temp1_input',    # Альтернативный путь 1
        f'{sys_path}/class/hwmon/hwmon1/temp1_input',    # Альтернативный путь 2
        '/sys/class/thermal/thermal_zone0/temp',         # Прямой путь
        '/sys/class/hwmon/hwmon0/temp1_input',           # Прямой путь 2
    ]

    for temp_path in possible_paths:
        try:
            if os.path.exists(temp_path):
                with open(temp_path, 'r') as f:
                    temp = int(f.read().strip())
                    # Температура может быть в миллиградусах или градусах
                    if temp > 1000:  # Если в миллиградусах
                        temp = temp / 1000.0
                    return f"{temp:.1f}°C"
        except:
            continue

    # Если не нашли температуру, пробуем через psutil (если доступно)
    try:
        if hasattr(psutil, "sensors_temperatures"):
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:  # Для Intel
                for entry in temps['coretemp']:
                    if 'Core' in entry.label:
                        return f"{entry.current:.1f}°C"
            elif 'cpu_thermal' in temps:  # Для ARM
                return f"{temps['cpu_thermal'][0].current:.1f}°C"
            elif temps:  # Любая первая температура
                for name, entries in temps.items():
                    if entries:
                        return f"{entries[0].current:.1f}°C"
    except:
        pass

    return "N/A"

def get_disk_info():
    """Получает информацию о дисках через команду df"""
    try:
        disks = []

        # Используем subprocess для получения вывода df
        try:
            # Запускаем df -hT и парсим вывод
            result = subprocess.run(['df', '-hT'], capture_output=True, text=True, check=True)
            lines = result.stdout.strip().split('\n')

            # Парсим строки (пропускаем заголовок)
            for line in lines[1:]:
                parts = line.split()
                if len(parts) >= 7:
                    device = parts[0]
                    fstype = parts[1]
                    total_str = parts[2]
                    used_str = parts[3]
                    percent_str = parts[5].replace('%', '')
                    mountpoint = parts[6]

                    # Пропускаем виртуальные файловые системы
                    if any(virtual in device for virtual in ['udev', 'tmpfs', 'efivarfs', 'devtmpfs', 'overlay', 'squashfs']):
                        continue

                    # Пропускаем временные файловые системы
                    if fstype in ['tmpfs', 'devtmpfs', 'squashfs']:
                        continue

                    # Пропускаем EFI разделы
                    if mountpoint.startswith('/boot/efi'):
                        continue

                    try:
                        # Конвертируем в байты
                        total_bytes = convert_to_bytes(total_str)
                        used_bytes = convert_to_bytes(used_str)
                        percent = float(percent_str)

                        # Определяем тип файловой системы
                        fs_info = get_filesystem_type_by_fstype(fstype, device, mountpoint)

                        disks.append({
                            'mountpoint': mountpoint,
                            'total': total_bytes,
                            'used': used_bytes,
                            'percent': percent,
                            'device': device,
                            'fstype': fstype,
                            'icon': fs_info['icon'],
                            'type': fs_info['type']
                        })

                    except Exception as e:
                        print(f"⚠️ Ошибка парсинга строки: {line} - {e}")
                        continue

        except subprocess.CalledProcessError as e:
            print(f"❌ Ошибка выполнения команды df -hT: {e}")
            # Fallback на psutil если df не работает
            return get_disk_info_fallback()

        # Сортируем по точке монтирования
        disks.sort(key=lambda x: x['mountpoint'])

        print(f"📊 Итог: найдено {len(disks)} разделов")
        return disks

    except Exception as e:
        print(f"❌ Ошибка получения информации о дисках: {e}")
        return get_disk_info_fallback()

def convert_to_bytes(size_str):
    """
    Конвертирует человеко-читаемый размер строки (например, "10G", "500M") в байты.
    """
    # Заменяем запятые на точки для правильного парсинга
    size_str = size_str.replace(',', '.')

    units = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}

    # Убираем нечисловые символы и определяем множитель
    size_str = size_str.upper().replace('B', '').replace('I', '')

    if size_str[-1] in units:
        number = float(size_str[:-1])
        unit = size_str[-1]
        return int(number * units[unit])
    else:
        return int(float(size_str) * 1024)  # Предполагаем килобайты

def get_filesystem_type_by_fstype(fstype, device, mountpoint):
    """
    Определяет более понятный тип файловой системы (например, 'Local', 'SMB', 'NFS')
    на основе типа файловой системы, устройства и точки монтирования.
    Возвращает словарь с иконкой и типом.
    """
    fstype_lower = fstype.lower()
    device_lower = device.lower()
    mountpoint_lower = mountpoint.lower()

    # SMB/CIFS разделы
    if fstype_lower in ['cifs', 'smb', 'samba']:
        return {'icon': '🌐', 'type': 'SMB'}

    # Проверяем по устройству (для монтирований где тип не указан как cifs)
    if '//' in device:
        return {'icon': '🌐', 'type': 'SMB'}

    # NFS разделы
    elif fstype_lower in ['nfs', 'nfs4']:
        return {'icon': '🖥️', 'type': 'NFS'}

    # Проверяем по устройству (nfs сервер:путь)
    elif ':' in device and '/' in device:
        return {'icon': '🖥️', 'type': 'NFS'}

    # SSHFS
    elif 'fuse.sshfs' in fstype_lower:
        return {'icon': '🔐', 'type': 'SSHFS'}

    # FUSE разделы
    elif 'fuse' in fstype_lower:
        # Проверяем по точке монтирования
        if any(x in mountpoint_lower for x in ['smb', 'samba', 'cifs', 'windows', 'nas', 'share']):
            return {'icon': '🌐', 'type': 'SMB (FUSE)'}
        elif any(x in mountpoint_lower for x in ['nfs', 'network']):
            return {'icon': '🖥️', 'type': 'NFS (FUSE)'}
        else:
            return {'icon': '🔗', 'type': 'FUSE'}

    # Локальные диски
    elif fstype_lower in ['ext4', 'ext3', 'ext2', 'xfs', 'btrfs', 'ntfs', 'vfat', 'exfat', 'apfs', 'hfs', 'zfs']:
        # Проверяем если это корневой раздел
        if mountpoint == '/':
            return {'icon': '💾', 'type': 'System'}
        elif mountpoint == '/boot':
            return {'icon': '🔧', 'type': 'Boot'}
        else:
            return {'icon': '💽', 'type': 'Local'}

    # Проверяем по точке монтирования (резервный метод)
    elif any(x in mountpoint_lower for x in ['smb', 'samba', 'cifs', 'windows', 'nas', 'share', 'mnt/smb', 'mnt/nas']):
        return {'icon': '🌐', 'type': 'SMB'}

    elif any(x in mountpoint_lower for x in ['nfs', 'network', 'mnt/nfs']):
        return {'icon': '🖥️', 'type': 'NFS'}

    # По умолчанию
    else:
        return {'icon': '📁', 'type': 'Other'}

def get_disk_info_fallback():
    """
    Резервная функция для получения информации о дисках с использованием psutil,
    если основной метод (через 'df') не работает или возвращает ошибку.
    """
    try:
        disks = []
        for partition in psutil.disk_partitions():
            try:
                # Пропускаем EFI разделы
                if partition.mountpoint.startswith('/boot/efi'):
                    continue

                usage = psutil.disk_usage(partition.mountpoint)
                fs_info = get_filesystem_type_by_fstype(partition.fstype, partition.device, partition.mountpoint)

                disks.append({
                    'mountpoint': partition.mountpoint,
                    'total': usage.total,
                    'used': usage.used,
                    'percent': usage.percent,
                    'device': partition.device,
                    'fstype': partition.fstype,
                    'icon': fs_info['icon'],
                    'type': fs_info['type']
                })
            except:
                continue
        return disks
    except:
        return []

def get_container_stats():
    """Получает статистику по Docker контейнерам"""
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)  # Все контейнеры включая остановленные

        running = 0
        stopped = 0

        for container in all_containers:
            if container.status == 'running':
                running += 1
            else:
                stopped += 1

        stats = {
            'total': len(all_containers),
            'running': running,
            'stopped': stopped
        }

        print(f"📊 Статистика контейнеров: {running} running, {stopped} stopped, {len(all_containers)} total")
        return stats

    except Exception as e:
        print(f"❌ Ошибка получения статистики контейнеров: {e}")
        return {'total': 0, 'running': 0, 'stopped': 0}

def get_detailed_container_stats():
    """Получает детальную статистику по Docker контейнерам"""
    try:
        client = docker.from_env()
        all_containers = client.containers.list(all=True)  # Все контейнеры включая остановленные
        
        containers_data = []
        
        for container in all_containers:
            try:
                # Получаем информацию о контейнере
                container_info = container.attrs
                
                # Получаем статистику контейнера
                stats = container.stats(stream=False)
                
                # Извлекаем информацию о CPU
                cpu_delta = stats.get('cpu_stats', {}).get('cpu_usage', {}).get('total_usage', 0)
                system_cpu_delta = stats.get('cpu_stats', {}).get('system_cpu_usage', 0)
                online_cpus = stats.get('cpu_stats', {}).get('online_cpus', 1)
                
                # Вычисляем использование CPU
                cpu_percent = 0
                if system_cpu_delta and cpu_delta:
                    cpu_percent = (cpu_delta / system_cpu_delta) * online_cpus * 100
                
                # Извлекаем информацию о памяти
                memory_usage = stats.get('memory_stats', {}).get('usage', 0)
                memory_limit = stats.get('memory_stats', {}).get('limit', 0)
                memory_percent = 0
                if memory_limit:
                    memory_percent = (memory_usage / memory_limit) * 100
                
                # Извлекаем информацию о дисковом I/O
                io_read = 0
                io_write = 0
                if 'blkio_stats' in stats:
                    for stat in stats['blkio_stats'].get('io_service_bytes_recursive', []):
                        if stat.get('op') == 'Read':
                            io_read += stat.get('value', 0)
                        elif stat.get('op') == 'Write':
                            io_write += stat.get('value', 0)
                
                # Извлекаем информацию о сети
                network_rx = 0
                network_tx = 0
                if 'networks' in stats:
                    for network_stats in stats['networks'].values():
                        network_rx += network_stats.get('rx_bytes', 0)
                        network_tx += network_stats.get('tx_bytes', 0)
                
                # Извлекаем количество процессов
                pids = stats.get('pids_stats', {}).get('current', 0)
                
                # Получаем имя контейнера
                container_name = container.name
                
                # Получаем иконку из метаданных контейнера
                icon = '🐳'  # Иконка по умолчанию
                if container_info.get('Config', {}).get('Labels'):
                    labels = container_info['Config']['Labels']
                    if 'dashboard.icon' in labels:
                        icon = labels['dashboard.icon']
                
                containers_data.append({
                    'id': container.id,
                    'name': container_name,
                    'status': container.status,
                    'icon': icon,
                    'cpu': cpu_percent,
                    'memory_used_mb': memory_usage / (1024 * 1024),
                    'memory_percent': memory_percent,
                    'io_read': io_read,
                    'io_write': io_write,
                    'network_rx': network_rx,
                    'network_tx': network_tx,
                    'pids': pids
                })
                
            except Exception as container_error:
                print(f"⚠️ Ошибка получения статистики для контейнера {container.name}: {container_error}")
                # Добавляем базовую информацию даже если статистика недоступна
                containers_data.append({
                    'id': container.id,
                    'name': container.name,
                    'status': container.status,
                    'icon': '🐳',
                    'cpu': 0,
                    'memory_used_mb': 0,
                    'memory_percent': 0,
                    'io_read': 0,
                    'io_write': 0,
                    'network_rx': 0,
                    'network_tx': 0,
                    'pids': 0
                })
        
        return containers_data
        
    except Exception as e:
        print(f"❌ Ошибка получения детальной статистики контейнеров: {e}")
        return []

def debug_disk_info():
    """Функция для отладки - показывает все точки монтирования"""
    print("🔍 ДИАГНОСТИКА ДИСКОВ:")
    try:
        for partition in psutil.disk_partitions():
            print(f"   Устройство: {partition.device}")
            print(f"   Точка монтирования: {partition.mountpoint}")
            print(f"   Тип ФС: {partition.fstype}")
            print(f"   Параметры: {partition.opts}")

            try:
                usage = psutil.disk_usage(partition.mountpoint)
                print(f"   Размер: {usage.total / 1024**3:.1f} GB")
                print(f"   Использовано: {usage.percent:.1f}%")
            except Exception as e:
                print(f"   ОШИБКА ДОСТУПА: {e}")

            print("   " + "-" * 50)
    except Exception as e:
        print(f"❌ Ошибка диагностики: {e}")

def get_local_ip_addresses():
    """
    Получает список локальных IP-адресов хоста, исключая loopback.
    Использует уже существующую функцию get_host_ip.
    """
    try:
        local_ips = []

        # Используем ту же функцию, что и для контейнеров
        host_ip = get_host_ip()

        if host_ip and host_ip != '127.0.0.1' and host_ip != '127.0.1.1':
            local_ips.append(host_ip)
            print(f"🌐 Используем IP: {host_ip}")
        else:
            print(f"⚠️ Получен невалидный IP: {host_ip}")

        return local_ips

    except Exception as e:
        print(f"❌ Ошибка получения IP: {e}")
        return []
