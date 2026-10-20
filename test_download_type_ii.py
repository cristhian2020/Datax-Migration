import sys
sys.path.append('d:/DATAX/data-processing-platform')
import os
import unittest
from robot import Robot
from download_tools import format_date

MAIN_URL = ''
UPDATED_TO = '2010-07-08'


class TestDownloadTypeII(unittest.TestCase):
    def setUp(self):
        self.robot = Robot()
        self.file_data = {
            'main_url': MAIN_URL,
            'path': os.curdir
        }

        self.files_list = self.robot.verify_download(
            main_url=self.file_data['main_url'], 
            updated_to=UPDATED_TO,
            path=self.file_data['path']
        )

    def test_verify_download(self):        

        self.assertIsInstance(self.files_list, list, "The result must be a list")
        self.assertTrue(len(self.files_list)>0, "At least one file must be downloaded")

        tmp_path = os.path.join(self.file_data['path'],'tmp')
        self.assertTrue(os.path.exists(tmp_path), "The function must to create a 'tmp' directory inside the main path.")

        expected_keys = {'tmp_path', 'download_url'}
        for item in self.files_list:
            self.assertIsInstance(item, dict, "Each item must be a dictionary")
            self.assertSetEqual(set(item.keys()),expected_keys, f"Each item must have only {expected_keys} keys")

            self.assertTrue(os.path.exists(item['tmp_path']), "The downloaded file must exist")
    
        updated_to = format_date(UPDATED_TO)

        result = self.robot.compare_files(files_paths=self.files_list,updated_to=UPDATED_TO)

        self.assertIsInstance(result, list, "The result must be a list")
        self.assertTrue(len(result)>0, "At least one file must pass the date filter")

        expected_keys = {'tmp_path', 'updated_to', 'download_url'}
        for item in result:
            self.assertIsInstance(item, dict, "Each item must be a dictionary")

            self.assertSetEqual(set(item.keys()),expected_keys, f"Each item must have only {expected_keys} keys")            
            
            result_updated_to = format_date(item['updated_to'])
            self.assertTrue(result_updated_to>updated_to,"The download date must be later than the reference date")
            
if __name__ == '__main__':
    unittest.main()