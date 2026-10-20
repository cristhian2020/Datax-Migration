import os
import re
from playwright.sync_api import sync_playwright

class Robot:
    """
    Robot de descarga Tipo III utilizando Playwright headless.
    """

    def verify_url(self, url, retries=3, wait_time=3, timeout=120, is_download_url=False):
        return True

    def get_file_url(self, main_url, updated_to, format='%Y-%m-%d'):
        urls = []
        with sync_playwright() as pl:
            browser = pl.chromium.launch(headless=True)
            context = browser.new_context(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)")
            page = context.new_page()
            page.goto(main_url, wait_until='load')

            # Espera explícita por la tabla
            page.wait_for_selector('table.report-table', timeout=15000)
            rows = page.query_selector_all('table.report-table tbody tr')

            for row in rows:
                link = row.query_selector('a')
                if link:
                    href = link.get_attribute('href')
                    if href and href.endswith('.xlsx'):
                        urls.append(href)

            browser.close()
        return urls

    def compare_files(self, files_paths, updated_to, format='%Y-%m-%d'):
        # Filtra archivos cuya fecha sea posterior a updated_to
        filtered = []
        for f in files_paths:
            fname = os.path.basename(f['tmp_path'])
            m = re.search(r'(\d{4}-\d{2}-\d{2})', fname)
            if m and m.group(1) > str(updated_to):
                f['updated_to'] = m.group(1)
                filtered.append(f)
        return filtered if filtered else False
