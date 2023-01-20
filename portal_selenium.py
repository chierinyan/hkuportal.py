import logging
LOG_FORMAT = '%(asctime)s: %(levelname)s %(message)s'
logging.basicConfig(level=logging.INFO, format=LOG_FORMAT)

from time import sleep

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.common.by import By
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.wait import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC

PORTAL_URL = 'https://hkuportal.hku.hk/login.html'

OPENING = 'https://sis-main.hku.hk/cs/sisprod/cache/PS_CS_STATUS_OPEN_ICN_1.gif'
CLOSED = 'https://sis-main.hku.hk/cs/sisprod/cache/PS_CS_STATUS_CLOSED_ICN_1.gif'
SUCCEED = 'https://sis-main.hku.hk/cs/sisprod/cache/PS_CS_STATUS_SUCCESS_ICN_1.gif'
FAILED = 'https://sis-main.hku.hk/cs/sisprod/cache/PS_CS_STATUS_ERROR_ICN_1.gif'

with open('pwd.txt', 'r') as f:
    USERNAME, PASSWORD = f.read().split('\n')[:2]

REFRESH_RATE = 7200
MAX_REATTEMPTS = 3
MAX_REFRESHES = 3
TIMEOUT = 60


def wait_and_find(frame, by, val, timeout=TIMEOUT):
    return WebDriverWait(frame, timeout).until(EC.presence_of_element_located((by, val)))


class Enrollee:
    def __init__(self):
        self.options = Options()
        self.options.add_argument("--headless")
        self.driver = None

    def start(self):
        try:
            self.driver.quit()
        except:
            pass

        self.driver = webdriver.Chrome(options=self.options)
        self.driver.get(PORTAL_URL)

        username_input = wait_and_find(self.driver, By.CSS_SELECTOR, '#username')
        password_input = wait_and_find(self.driver, By.CSS_SELECTOR, '#password')
        submit = wait_and_find(self.driver, By.CSS_SELECTOR, '#login_btn')

        username_input.send_keys(USERNAME)
        password_input.send_keys(PASSWORD)
        submit.click()

        add_class_link = wait_and_find(self.driver, By.CSS_SELECTOR, '#crefli_Z_HC_SSR_SSENRL_CART_LNK > a')
        add_class_link.click()

    def check_status(self, sems):
        sem_ids = {1: 'SSR_DUMMY_RECV1$sels$0$$0', 2: 'SSR_DUMMY_RECV1$sels$1$$0'}

        class_exists = False
        for sem in sems:
            self.driver.refresh()
            logging.info(f'Sem {sem} refreshed')

            frame = wait_and_find(self.driver, By.CSS_SELECTOR, '#ptifrmtgtframe')
            self.driver.switch_to.frame(frame)

            sem_option = wait_and_find(self.driver, By.XPATH, f'//*[@id="{sem_ids[sem]}"]')
            continue_button = wait_and_find(self.driver, By.CSS_SELECTOR, '#DERIVED_SSS_SCT_SSR_PB_GO')
            sem_option.click()
            continue_button.click()

            temporary_list = WebDriverWait(self.driver, TIMEOUT).until(EC.presence_of_all_elements_located(
                (By.XPATH, '//*[@id="SSR_REGFORM_VW$scroll$0"]//table//tr')))[1:]

            if temporary_list[0].find_element(By.CSS_SELECTOR, 'div').get_attribute('id') == 'win0divP_NO_CLASSES$0':
                logging.warning('No class in temporary list')
                continue
            else:
                class_exists = True

            for course in temporary_list:
                course_name = wait_and_find(course, By.CSS_SELECTOR, '[id^=P_CLASS_NAME]').text.split('\n')[0]
                course_status = wait_and_find(course, By.CSS_SELECTOR, '[id^=win0divDERIVED_REGFRM1_SSR_STATUS_LONG] img')
                course_status_img = course_status.get_attribute('src')

                if course_status_img == OPENING:
                    logging.warning(f'{course_name} opening, selection proceeding\7')
                    enrol_result = self.proceed()
                    return enrol_result
                elif course_status_img == CLOSED:
                    logging.info(f'{course_name} is closed')
                else:
                    logging.error(f'Course {course_name}: Unknow status')
                    print(course_status_img)

        if not class_exists:
            logging.critical('No class in selected sems')
            exit(0)

        logging.info(f'Will refresh in {REFRESH_RATE} seconds\n')
        sleep(REFRESH_RATE)
        return 0

    def proceed(self):
        proceed = wait_and_find(self.driver, By.XPATH, f'//*[@id="DERIVED_REGFRM1_LINK_ADD_ENRL$82$"]')
        proceed.click()

        try:
            errmsg = wait_and_find(self.driver, By.XPATH, '//*[@id="DERIVED_SASSMSG_ERROR_TEXT$0"]', timeout=10)
            raise Exception(errmsg.text)
        except TimeoutException:
            pass

        finish = wait_and_find(self.driver, By.CSS_SELECTOR, '#DERIVED_REGFRM1_SSR_PB_SUBMIT')
        finish.click()

        results = WebDriverWait(self.driver, TIMEOUT).until(EC.presence_of_all_elements_located(
            (By.XPATH, '//*[@id="SSR_SS_ERD_ER$scroll$0"]/tbody/tr/td/table/tbody/tr')))
        results = results[1:]

        all_failed = True
        for result in results:
            result_name = wait_and_find(result, By.CSS_SELECTOR, '[id^=win0divR_CLASS_NAME] > span').text
            result_message = wait_and_find(result, By.CSS_SELECTOR, '[id^=win0divDERIVED_REGFRM1_SS_MESSAGE_LONG] > div').text
            result_status = wait_and_find(result, By.CSS_SELECTOR, '[id^=win0divDERIVED_REGFRM1_SSR_STATUS_LONG] img').get_attribute('src')

            if result_status == SUCCEED:
                logging.warning(f'{result_name} Submitted for approval')
                all_failed = False
            elif result_status == FAILED:
                logging.error(f'Unable to add {result_name}:\n{result_message}')

        if all_failed:
            return 1

        return 0


def main():
    reattempts = 0
    while True:
        try:
            enrollee = Enrollee()
            enrollee.start()

            refreshes = 0
            while refreshes < MAX_REFRESHES:
                check_result = enrollee.check_status([1,2])
                if check_result == 1:
                    refreshes += 1
                    logging.warning(f'Retrying {refreshes}/{MAX_REFRESHES}')
                    continue

                reattempts = 0
                refreshes = 0

            raise Exception('Reached maximum refreshes')

        except Exception:
            logging.exception('')
            reattempts += 1

            if reattempts > MAX_REATTEMPTS:
                logging.warning(f'Reached maximum reattempts, will retry in {REFRESH_RATE} seconds\7\n')
                sleep(REFRESH_RATE)

            logging.warning(f'Restarting webdriver {reattempts}/{MAX_REATTEMPTS}')


if __name__ == '__main__':
    main()

