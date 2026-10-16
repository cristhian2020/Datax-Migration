import sys
sys.path.append('d:/DATAX/data-processing-platform')
import os
import unittest
import requests
import shutil
import warnings
import urllib
import time
import mimetypes
from datetime import datetime
from urllib.parse import urlparse
from robot import Robot
from download_tools import format_date

MAIN_URL = ''
UPDATED_TO = '2010-07-08'

def is_valid_url (url:str) -> bool:
    parsed = urlparse(url)
    return all([parsed.scheme in ['http', 'https'], parsed.netloc])

def file_download(urls, path, wait_time=2):
        """
        Downloads a file from the given URL(s) to the specified path and optionally renames it.

        Parameters:
            urls (list of string): List of URLs of the files to be downloaded.
            path (string): Path where the downloaded files will be saved.
            rename (string, optional): Optional new name for the downloaded file(s).

        Returns:
            list: List of dictionaries containing information about files that meet the criteria.
        """
        file_paths = []

        # Ignore Unverified HTTPS request warning
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")

            # Erase the previous tmp path and create the a new one 
            path = os.path.join(path, 'tmp')
            if os.path.exists(path):
                shutil.rmtree(path)
            os.makedirs(path)

            for url in urls:
                print(f"Downloading: {url} ...")
                # Parse the URL to extract the file name and extension
                parsed_url = urllib.parse.urlparse(url)
                file_name = os.path.basename(parsed_url.path)
                extension = os.path.splitext(file_name)[1]

                # Make a request to the URL
                response = requests.get(url, verify=False, headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9',
                }
                )

                # If the extension is not provided, try to guess it from the content-type header
                if 200 <= response.status_code < 300:
                    if not extension:
                        extension = mimetypes.guess_extension(response.headers['content-type'])
                        file_name += extension

                    date_now = datetime.now()
                    date_now = date_now.strftime("%Y-%m-%d_%H%M%S")
                    # Combine the file name with the file path
                    file_name = date_now + file_name
                    file_path = os.path.join(path, file_name)

                    # Download the file
                    with open(file_path, "wb") as f:
                        f.write(response.content)

                    # Append the file path to the list
                    file_paths.append({
                        "download_url": url,
                        "tmp_path": file_path})

                    # Wait for the specified time before the next download
                    time.sleep(wait_time)
        
        # If the list of verified_urls is empty returns NONE
        if not len(file_paths):
            print("Could not download any file")
            return False
        return file_paths

class TestDownloadTypeI(unittest.TestCase):
    def setUp(self):
        self.robot = Robot()
        self.file_data = {'main_url': MAIN_URL}
        reference_date = UPDATED_TO

        self.file_urls = self.robot.get_file_url(
            main_url=self.file_data['main_url'], 
            updated_to=reference_date
        )

    def test_get_file_url(self):        

        self.assertIsInstance(self.file_urls, list, "The result must be a list")
        self.assertTrue(len(self.file_urls)>0, "At least one file must be scraped")

        for item in self.file_urls:
            self.assertIsInstance(item, str, "Each item must be a URL string")
            self.assertTrue(is_valid_url(item), f"Invalid URL format: {item}")
    
        updated_to = format_date(UPDATED_TO)

        files_downloaded = file_download(urls=self.file_urls,path=os.curdir)
        result = self.robot.compare_files(files_paths=files_downloaded,updated_to=UPDATED_TO)

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