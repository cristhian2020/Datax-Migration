import sys
sys.path.append('d:/DATAX/data-processing-platform')
import os
import unittest
from robot import Robot
from download_tools import format_date

MAIN_URL = ''
UPDATED_TO = '2010-07-08'

class TestDownloadTypeIII(unittest.TestCase):
    def setUp(self):
        self.robot = Robot()
        self.file_data = {
            'main_url': MAIN_URL,
            'path': os.curdir,
            'key_words': 'test'
        }

    def test_check_new_data(self):
        updated_to = format_date(UPDATED_TO)
        
        result = self.robot.check_new_data(main_url=self.file_data['main_url'], updated_to=UPDATED_TO ,path=self.file_data['path'],key_words=self.file_data['key_words'])

        self.assertIsInstance(result, list, "The result must be a list")
        self.assertTrue(len(result)>0, "At least one file must be downloaded")

        tmp_path = os.path.join(self.file_data['path'],'tmp')
        self.assertTrue(os.path.exists(tmp_path), "The function must to create a 'tmp' directory inside the main path.")

        expected_keys = {'tmp_path', 'updated_to', 'download_url'}
        for item in result:
            self.assertIsInstance(item, dict, "Each item must be a dictionary")

            self.assertSetEqual(set(item.keys()),expected_keys, f"Each item must have only {expected_keys} keys")

            self.assertTrue(os.path.exists(item['tmp_path']), "The downloaded file must exist")
            
            result_updated_to = format_date(item['updated_to'])
            self.assertTrue(result_updated_to>updated_to,"The download date must be later than the reference date")

if __name__ == '__main__':
    unittest.main()