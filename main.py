import requests
import json
import logging
from urllib.parse import quote

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')


class DogBackupUploader:
    def __init__(self, breed: str, yandex_token: str):
        # Инициализация параметров: породы, токена, API и статистики
        self.breed = breed.lower()
        self.token = yandex_token
        self.ya_headers = {
            'Authorization': f'OAuth {self.token}'
        }
        self.api_base = 'https://dog.ceo/api'  # API для получения изображений
        self.yandex_api_base = 'https://cloud-api.yandex.net/v1/disk/resources'  # API Яндекс.Диска
        self.uploaded_files = []  # Список загруженных файлов
        self.stats = {"uploaded": 0, "skipped": 0}  # Статистика загрузок

    def get_sub_breeds(self):
        # Получаем список под-пород для указанной породы
        url = f'{self.api_base}/breed/{self.breed}/list'
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()['message']
        else:
            logging.error("Не удалось получить под-породы")
            return []

    def get_image_url(self, breed, sub_breed=None):
        # Получаем ссылку на случайное изображение указанной породы или под-породы
        if sub_breed:
            url = f'{self.api_base}/breed/{breed}/{sub_breed}/images/random'
        else:
            url = f'{self.api_base}/breed/{breed}/images/random'
        response = requests.get(url)
        if response.status_code == 200:
            return response.json()['message']
        else:
            logging.error(f"Не удалось получить картинку для {breed}/{sub_breed}")
            return None

    def create_yadisk_folder(self):
        # Создаем папку на Яндекс.Диске в структуре /dogs/<порода>
        base = '/dogs'
        breed_path = f'{base}/{self.breed}'

        # Создаем базовую папку /dogs
        requests.put(f'{self.yandex_api_base}?path={quote(base)}', headers=self.ya_headers)

        # Создаем папки /dogs/<порода>
        response = requests.put(f'{self.yandex_api_base}?path={quote(breed_path)}', headers=self.ya_headers)
        if response.status_code in [201, 409]:
            return breed_path
        else:
            logging.error("Не удалось создать папку на Яндекс.Диске")
            return None

    def file_exists_on_yadisk(self, path):
        # Проверяем, существует ли файл по заданному пути
        check_url = f"{self.yandex_api_base}?path={quote(path)}"
        resp = requests.get(check_url, headers=self.ya_headers)
        return resp.status_code == 200

    def upload_image_to_yadisk(self, image_url, folder_path, image_name):
        # Загрузка изображения на Яндекс.Диск по полученной ссылке
        target_path = f'{folder_path}/{image_name}'

        if self.file_exists_on_yadisk(target_path):
            logging.info(f"Пропущено (уже существует): {image_name}")
            self.uploaded_files.append({"file_name": image_name, "skipped": True})
            self.stats["skipped"] += 1
            return

        # Скачиваем изображение в память
        try:
            image_data = requests.get(image_url).content
        except Exception as e:
            logging.error(f"Ошибка скачивания изображения: {e}")
            return

        # Получаем ссылку для загрузки на Диск
        upload_link_resp = requests.get(
            'https://cloud-api.yandex.net/v1/disk/resources/upload',
            headers=self.ya_headers,
            params={
                'path': target_path,
                'overwrite': 'true'
            }
        )

        if upload_link_resp.status_code != 200:
            logging.error(f"Не удалось получить ссылку загрузки: {upload_link_resp.status_code}")
            return

        href = upload_link_resp.json().get('href')
        if not href:
            logging.error("Пустая ссылка загрузки")
            return

        # Загрузка изображения на Яндекс.Диск
        upload_resp = requests.put(href, data=image_data)
        if upload_resp.status_code in [201, 202]:
            logging.info(f"Загружено: {image_name}")
            self.uploaded_files.append({"file_name": image_name, "skipped": False})
            self.stats["uploaded"] += 1
        else:
            logging.error(f"Ошибка загрузки файла: {upload_resp.status_code}")

    def backup(self):
        # загрузка изображений под-пород на Яндекс.Диск
        folder = self.create_yadisk_folder()
        if not folder:
            return

        # Получаем список под-пород, если их нет — используем саму породу
        sub_breeds = self.get_sub_breeds()
        if not sub_breeds:
            sub_breeds = [None]

        total = len(sub_breeds)
        for i, sub in enumerate(sub_breeds, start=1):
            print(f"[{i}/{total}] Обработка под-породы: {sub if sub else self.breed}")
            image_url = self.get_image_url(self.breed, sub)
            if image_url:
                name_part = sub if sub else self.breed
                image_filename = name_part + "_" + image_url.split("/")[-1]
                self.upload_image_to_yadisk(image_url, folder, image_filename)

        # Сохраняем список загруженных и пропущенных файлов
        with open("uploaded_images.json", "w") as f:
            json.dump(self.uploaded_files, f, indent=2, ensure_ascii=False)

        # Вывод финальной статистики
        print(f"Готово! Загружено: {self.stats['uploaded']}, пропущено (уже было): {self.stats['skipped']}")


if __name__ == '__main__':
    # Запрашиваем породу и токен у пользователя
    breed = input("Введите название породы (напр. spaniel): ").strip().lower()
    token = input("Введите OAuth-токен Яндекс.Диска: ").strip()

    # Запускаем загрузку изображений
    uploader = DogBackupUploader(breed, token)
    uploader.backup()
