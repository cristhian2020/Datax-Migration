import sys
sys.path.append('d:/DATAX/data-processing-platform')
import os
import unittest
from robot import Robot

MAIN_URL = ''
UPDATED_TO = '2010-07-08'

class TestDownloadTypeIV(unittest.TestCase):
    def setUp(self):
        self.robot = Robot()
        self.file_data = {
            'main_url': MAIN_URL,
            'path': os.curdir
        }

        self.files_path = self.robot.get_data(main_url=self.file_data['main_url'], path=self.file_data['path'], updated_to=UPDATED_TO)

    def test_check_new_data(self): 

        tmp_path = os.path.join(self.file_data['path'],'tmp')
        self.assertEqual(tmp_path,self.files_path, "The result must be a tmp directory inside the main path")
        self.assertTrue(os.path.exists(self.files_path), "The result must exists.")

        list_files = os.listdir(self.files_path)
        self.assertTrue(len(list_files)>0, "At least one file must be downloaded")

        for item in list_files:

            self.assertRegex(item, r'^\d{4}-\d{2}-\d{2}', "Each file must have the date at the start of the name file")
            item_path = os.path.join(self.files_path, item)
            self.assertTrue(os.path.isfile(item_path), "The item must be a file")            

if __name__ == '__main__':
    unittest.main()