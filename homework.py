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
    except exceptions.SendMessageFailure:
        logger.error('Сбой при отправке сообщения в чат')


def get_api_answer(current_timestamp):
    """Запрос к эндпоинту API-сервиса."""
    timestamp = current_timestamp
    params = {'from_date': timestamp}
    try:
        response = requests.get(ENDPOINT, headers=HEADERS, params=params)
    except exceptions.APIResponseStatusCodeException:
        logger.error('Сбой при запросе к эндпоинту')
    if response.status_code != HTTPStatus.OK:
        msg = 'Сбой при запросе к эндпоинту'
        logger.error(msg)
        raise exceptions.APIResponseStatusCodeException(msg)
    return response.json()


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
    try:
        homework_name = homework.get('homework_name')
    except KeyError as e:
        msg = f'Ошибка доступа по ключу homework_name: {e}'
        logger.error(msg)
    try:
        homework_status = homework.get('status')
    except KeyError as e:
        msg = f'Ошибка достпа по ключу status: {e}'
        logger.error(msg)

    verdict = HOMEWORK_STATUSES[homework_status]
    if verdict is None:
        msg = 'Неизвестен статус домашенй работы'
        logger.error(msg)
        raise exceptions.UnknownHWStatusException(msg)
    return f'Изменился статус проверки работы "{homework_name}". {verdict}'


def check_tokens():
    """Проверка наличия токенов."""
    return all([TELEGRAM_TOKEN, TELEGRAM_CHAT_ID, PRACTICUM_TOKEN])


def main():
    """Основная логика работы бота."""
    if not check_tokens():
        msg = 'Проблема с токенами'
        logger.critical(msg)
        raise exceptions.MissingRequiredTokenException(msg)

    bot = telegram.Bot(token=TELEGRAM_TOKEN)
    current_timestamp = int(time.time() - 604800)
    previous_status = None
    previous_error = None

    while True:
        try:
            response = get_api_answer(current_timestamp)
        except exceptions.IncorrectAPIResponseException as e:
            if str(e) != previous_error:
                previous_error = str(e)
                send_message(bot, e)
            logger.error(e)
            time.sleep(RETRY_TIME)
            continue
        try:
            homeworks = check_response(response)
            homework_status = homeworks[0].get('status')
            if homework_status != previous_status:
                previous_status = homework_status
                message = parse_status(homeworks[0])
                send_message(bot, message)
            else:
                logger.debug('Без обновлений')

            time.sleep(RETRY_TIME)

        except Exception as error:
            message = f'Сбой в работе программы: {error}'
            if previous_error != str(error):
                previous_error = str(error)
                send_message(bot, message)
            logger.error(message)
            time.sleep(RETRY_TIME)


if __name__ == '__main__':
    main()
