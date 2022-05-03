import logging
import os
import time
import telegram
from dotenv import load_dotenv
import exceptions
import requests
from http import HTTPStatus

load_dotenv()

PRACTICUM_TOKEN = os.getenv('PRACTICUM_TOKEN')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

RETRY_TIME = 600
ENDPOINT = 'https://practicum.yandex.ru/api/user_api/homework_statuses/'
HEADERS = {'Authorization': f'OAuth {PRACTICUM_TOKEN}'}


HOMEWORK_STATUSES = {
    'approved': 'Работа проверена: ревьюеру всё понравилось. Ура!',
    'reviewing': 'Работа взята на проверку ревьюером.',
    'rejected': 'Работа проверена: у ревьюера есть замечания.'
}

logging.basicConfig(
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s',
    level=logging.INFO,
)

logger = logging.getLogger(__name__)
handler = logging.StreamHandler()
logger.addHandler(handler)


def send_message(bot, message):
    """Отправка сообщений в чат."""
    try:
        bot.send_message(chat_id=TELEGRAM_CHAT_ID, text=message)
        logger.info('Сообщение в чат отправлено')
    except telegram.error.TelegramError:
        logger.error('Сбой при отправке сообщения в чат')


def get_api_answer(current_timestamp):
    """Запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp or int(time.time())
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except requests.RequestException:
        logger.error('Сбой при запросе к эндпоинту')
    if response.status_code != HTTPStatus.OK:
        msg = 'Сбой при запросе к эндпоинту'
        logger.error(msg)
        raise requests.HTTPError(msg)
    try:
        return response.json()
    except ValueError:
        logger.error('Ошибка парсинга ответа из формата json')
        raise ValueError('Ошибка парсинга ответа из формата json')


def check_response(response):
    """Проверка корректности ответа API."""
    try:
        homework_list = response['homeworks']
    except KeyError as e:
        msg = f'Обшибка доступа по ключу homeworks: {e}'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if homework_list is None:
        msg = 'В ответе API-сервиса нет словаря с домашними работами'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if len(homework_list) == 0:
        msg = 'Не было домашних работ за последнее время'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    if not isinstance(homework_list, list):
        msg = 'В ответе API домашние работы - не список'
        logger.error(msg)
        raise exceptions.CheckResponseException(msg)
    return homework_list


def parse_status(homework):
    """Получение информации о домашней работе и ее статус."""
    if 'homework_name' not in homework:
        raise KeyError('Отсутствует ключ "homework_name" в ответе API')
    if 'status' not in homework:
        raise Exception('Отсутствует ключ "status" в ответе API')
    homework_name = homework['homework_name']
    homework_status = homework['status']
    if homework_status not in HOMEWORK_STATUSES:
        raise Exception(f'Неизвестный статус работы: {homework_status}')
    verdict = HOMEWORK_STATUSES[homework_status]
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка наличия токенов."""
    return all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PRACTICUM_TOKEN])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        raise SystemExit

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - 604800)
    previous_status = None
    previous_error = None

    while True:
        response = get_api_answer(current_timestamp)
        try:
            homeworks = check_response(response)
            homework_status = homeworks[0].get('status')
            if homework_status != previous_status:
                previous_status = homework_status
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Без обновлений')
        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if previous_error != str(error):
                previous_error = str(error)
                send_message(bot, message)
            logger.error(message)
        finally:
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
