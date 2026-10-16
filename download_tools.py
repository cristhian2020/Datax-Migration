import csv
import random
import os
from datetime import datetime
import calendar
import re
import pandas as pd
import fitz
import datetime as dt
from openpyxl import load_workbook
from unidecode import unidecode
import ntpath       #path library for windows
import posixpath  #  path library fo Unix/Linux

# *GENERIC FUNCTIONS

def get_proxy():
    """
    Retrieves a random proxy from the 'Verified_proxys.csv' file along with predefined headers.

    Returns:
        dict: A dictionary containing the proxy and headers.
            {
                'proxy': str,  # Randomly selected proxy
                'header': {
                    'User-Agent': str,  # User-Agent header
                    'Accept': str,  # Accept header
                    'Accept-Encoding': str,  # Accept-Encoding header
                    'Accept-Language': str,  # Accept-Language header
                }
            }
    """
    with open('Verified_proxys.csv', 'r') as f:
        reader = csv.reader(f)
        lines = list(reader)
        random_proxy = random.choice(lines)[0]
        return {
            'proxy': random_proxy,
            'header': {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/89.0.4389.82 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9',
                'Accept-Encoding': 'gzip, deflate, br',
                'Accept-Language': 'en-US,en;q=0.9',
            }
        }


def createDirectoryStruct(file_date, base_path, publication_frequency, format='%Y-%m-%d'):
    """
    Creates directory structure where the file will be saved.

    Args:
        file_date (str): Date of the file data, expressed in YYYY-MM-DD format.
        base_path (str): Base path where the files will be stored.
        publication_frequency (str): Frequency of data of the file.
        format (str, optional): Format of the date string. Defaults to '%Y-%m-%d'.

    Returns:
        str: Absolute path of the created directory structure.
    """
    level_1_frecuency = ['mensual', 'trimestral', 'semestral', 'anual']
    level_2_frecuency = ['diario', 'semanal']

    try:

        fileDate = datetime.strptime(file_date, format) if isinstance(file_date,str) else file_date

    except ValueError as e:
        print(f"Date can not be procesed")
        return base_path

    if publication_frequency.lower() in level_2_frecuency:
        # For daily and weekly frequency, create directory structure up to month level
        filePath = os.path.join(base_path, str(fileDate.year))
        filePath = os.path.join(filePath, str(
            fileDate.year) + "-" + str("%02d" % (fileDate.month,)))
    elif publication_frequency.lower() in level_1_frecuency:
        # For monthly, quarterly, semi-annual, and annual frequency, create directory structure up to year level
        filePath = os.path.join(base_path, str(fileDate.year))
    else:
        # If the publication frequency is not recognized, return base path
        filePath = base_path
        print("Publication frecuency uwknomed")
    # Create the directory if it doesn't exist
    if not os.path.exists(filePath):
        os.makedirs(filePath)
    return filePath


# * ESPECIFIC FUCNTIONS

def format_date(date, format='%Y-%m-%d'):
    """
    Formats the given date string into a datetime object.

    Args:
        date (str): The date string to be formatted.
        format (str): The format of the date string. Default is '%Y-%m-%d'.

    Returns:
        datetime.datetime: The formatted datetime object.
    """
    try:
        # Convert updated_to string to datetime object
        date_formated = datetime.strptime(date, format)
        return date_formated
    except ValueError as e:
        print(f"Date can not be procesed")
        return date


def month_to_number(month):
    """
    Converts a month name into its corresponding number.

    Args:
        month (str): The name of the month.

    Returns:
        int: The numerical representation of the month (1 for January, 2 for February, etc.).
            Returns None if the given month name is not found.
    """
    months = {
        "enero": 1,
        "febrero": 2,
        "marzo": 3,
        "abril": 4,
        "mayo": 5,
        "junio": 6,
        "julio": 7,
        "agosto": 8,
        "septiembre": 9,
        "setiembre": 9,
        "octubre": 10,
        "noviembre": 11,
        "diciembre": 12
    }

    return months.get(month.lower())


def month_abr_to_number(month):
    """
    Converts an abbreviated month name into its corresponding number.

    Args:
        month (str): The abbreviated name of the month.

    Returns:
        int: The numerical representation of the month (1 for January, 2 for February, etc.).
            Returns None if the given month abbreviation is not found.
    """
    months = {
        "ENE": 1,
        "FEB": 2,
        "MAR": 3,
        "ABR": 4,
        "MAY": 5,
        "JUN": 6,
        "JUL": 7,
        "AGO": 8,
        "SEP": 9,
        "OCT": 10,
        "NOV": 11,
        "DIC": 12,
        "JAN": 1,
        "APR": 4,
        "AUG": 8,
        "DEC": 12,
        "SET":9
    }

    return months.get(month.upper())


def text_extract(pdf_path):
    """
    Extracts text from a PDF file.

    Args:
        pdf_path (str): The path to the PDF file.

    Returns:
        str: The extracted text from the PDF.
    """
    text = ""
    document = fitz.open(pdf_path)
    for page in document:
        text += page.get_text()

    text = text.split("\n")
    return text


def last_day_month(year, month):
    """
    Returns the last day of the given month and year.

    Args:
        year (int): The year.
        month (int): The month.

    Returns:
        int: The last day of the month.
    """
    return calendar.monthrange(year, month)[1]


def last_day_week(date):
    """
    Returns the last day of the week for the given date.

    Args:
        date (datetime.date): The date.

    Returns:
        datetime.date: The last day of the week.
    """
    return date + dt.timedelta(days=(6 - date.weekday()))


def compare_with_last_file(last_file_path, new_file_path, type="excel"):
    """
    Compares two files to check if they are identical.

    Args:
        last_file_path (str): The path to the previous file.
        new_file_path (str): The path to the new file.
        type (str, optional): The type of files to compare. Defaults to "excel".

    Returns:
        bool: True if the files are identical, False otherwise.
    """

    if type == 'excel':
        dfs_last_file = pd.read_excel(last_file_path, sheet_name=None)
        dfs_new_file = pd.read_excel(new_file_path, sheet_name=None)

        # Compare each sheet in both files
        for sheet_name in dfs_new_file.keys():
            if sheet_name not in dfs_last_file:
                return False

            # Check if the data in each cell are equal
            if not dfs_new_file[sheet_name].equals(dfs_last_file[sheet_name]):
                return False

        return True

    if type == 'pdf':

        # Extract text from both PDF files
        text_last_file = text_extract(last_file_path)
        text_new_file = text_extract(new_file_path)

        # Compare texts
        if text_last_file == text_last_file:
            return True
        else:
            return False



def get_date_method_1(dataframe):
    """
    Extracts the dataframe date, searching the last records in the table.

    Args:
        dataframe (pd.DataFrame): The input DataFrame containing date information.

    Returns:
        list: A list containing the extracted date components (int) [month, year].
    """
     # Check if the first column is entirely NaN or starts with 'Unnamed'
    if dataframe[dataframe.columns[0]].isna().all() or dataframe.columns[0].startswith('Unnamed'):
        # Drop the first column if it doesn't contain useful information
        dataframe.drop(columns=[dataframe.columns[0]], inplace=True)
    
    # Regular expressions to match months and years
    re_month = r"\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b"
    re_year = r'^(\d{4})\s*[(]?p?[)]?'

    # Get the first and second column names
    first_column = dataframe.columns[0]
    second_column = dataframe.columns[1]

    # Extract the date information from the first column
    sub_set = dataframe[first_column]
    year_set = [re.findall(re_year, str(year))[0] for year in sub_set if re.findall(re_year, str(year)) and len(str(year).strip())<=7]
    
    # If no valid years are found in the first column, try the second column
    if not len(year_set):
        sub_set = dataframe[second_column]
        year_set = [re.findall(re_year, str(year))[0] for year in sub_set if re.findall(re_year, str(year)) and len(str(year).strip())<=7]
    
    # Filter out years that are too old
    year_set = [year for year in year_set if int(year)>datetime.now().year-10]

     # Initialize a list to store extracted months
    month_set = []
    for index, month in enumerate(sub_set):
            month_str= str(month).strip().lower()
            match = re.findall(re_month, month_str)
            # data_side = dataframe[dataframe.columns[2]].iloc[index]

            # Check if a valid month is found and if the value is alphabetic
            if match and bool(re.match(r'^[a-zA-Z]+$',str(month_str))) :
                month_set.append(match[0])

    # If no valid months are found in the first column, try the second column
    if not len(month_set):
        sub_set = dataframe[second_column]
        for index, month in enumerate(sub_set):
            month_str= str(month).strip().lower()
            match = re.findall(re_month, month_str)
            # data_side = dataframe[dataframe.columns[2]].iloc[index]

            # Check if a valid month is found and if the value is alphabetic
            if match and bool(re.match(r'^[a-zA-Z]+$',str(month_str))) :
                month_set.append(match[0])

    # If no valid months or years are found, return an empty list
    if (not len(year_set)) or (not len(month_set)):
        return []
    
    # Extract the most recent year
    year = year_set[-1]
    year = int(year)
    
    # Extract the most recent month
    month = month_set[-1]
    month = month_to_number(month) if month_to_number(month) else month_abr_to_number(month)

    return [month, year]


def get_date_method_5(dataframe):
    if dataframe[dataframe.columns[0]].isna().all():
    # Eliminar la columna "Columna1"
        dataframe.drop(columns=[dataframe.columns[0]], inplace=True)
    re_date = r"\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b\s*\d{4}"
    first_column = dataframe.columns[0]
    sub_set = dataframe[first_column]
    # sub_set = sub_set.str.strip()
    date_set = [str(date) for date in sub_set if re.search(re_date, str(date).lower())]
    
    if not len(date_set):
        return []
    date = re.split(r'\s|[\xa0]', date_set[-1])
    year = int(date[1])
    
    month = str(date[0]).strip()
    month = month_to_number(month) if month_to_number(month) else month_abr_to_number(month)

    return [month, year]

def get_date_method_2(dataframe, init_index=0, final_index=10):
    """
    Extracts the date information from the DataFrame.

    Args:
        dataframe (pd.DataFrame): The input DataFrame containing date information.
        init_index (int, optional): The starting index of rows to search for dates. Defaults to 0.
        final_index (int, optional): The final index of rows to search for dates. Defaults to 10.

    Returns:
        list: A list containing the extracted date components (int) [month, year].
    """
    # Regular expression to match different date formats
    re_date = r"(\d{4}-\d{2}-\d{2})|(\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic\b)\s*(?:de)?\s*\d{4})|(\b(?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic)\b)|(^\b\d{4})\s*[(]?p?[)]?$"

    # Extract a subset of rows from the DataFrame to search for dates
    dataframe_to_look = dataframe.iloc[init_index:final_index + 1]

    matches = []
    for column in dataframe_to_look.columns:
        for index, value in dataframe_to_look[column].items():
            # Convert the value to lowercase and strip whitespace
            value_str = str(value).strip().lower()
            # Search for matches of the date pattern in the value string    
            match_value = re.search(re_date,value_str)
            matches.append(match_value)

    # Filter out None matches
    matches = [match for match in matches if match]
    
    if not matches:
        return []
    
    # Extract dates in "YYYY-MM-DD" format
    dates = [match.group(1) for match in matches if match.group(1)]
    
    if len(dates):
        # Process dates in "YYYY-MM-DD" format
        date = dates[-1]
        date = re.split(r'-', date)
        year = int(date[0])
        month = int(date[1])
        return [month,year]
    
    # Extract dates in "Month Year" format
    dates_string = [match.group(2) for match in matches if match.group(2)]
    if len(dates_string):
        # Process dates in "Month Year" format
        date = dates_string[-1]
        date = re.split(r'\s|[\xa0]', date)
        if 'de' in date:
            date.remove('de')
        month = month_to_number(date[0]) if month_to_number(date[0]) else month_abr_to_number(date[0])

        year = int(date[1]) 
        return [month, year]
    
    # Extract years without month information
    months = [match.group(3) for match in matches if match.group(3)]
    years = sorted([match.group(4) for match in matches if match.group(4) and int(match.group(4))<=datetime.now().year])
    
    if (not len(years)) or (not len(months)):
        return []
    
    # Process extracted year and month
    year = int(years[-1])
    month = months[-1]
    month = month_to_number(month) if month_to_number(month) else month_abr_to_number(month)
    return [month,year]

def get_date(dataframe):
    """
    Extracts a date from the specified range of rows in the given DataFrame.

    Args:
        dataframe (pandas.DataFrame): The DataFrame to search for the date.
        init_index (int, optional): The starting index to search for the date. Defaults to 0.
        final_index (int, optional): The ending index to search for the date. Defaults to 3.

    Returns:
        list: A list containing the extracted date components [month, year].
    """
    date = []

    # Attempt different methods to extract the date
    methods = [
        get_date_method_1,
        get_date_method_2,
        get_date_method_5
    ]

    for method in methods:
        date = method(dataframe)
        if date:
            print(f"Using {method.__name__}")
            return date

    return date
    


def delete_hidden_sheets(file):
    
    workbook = load_workbook(file)

    # Recorre todas las hojas del archivo
    for sheet in workbook.sheetnames:
        # Obtiene la hoja actual
        current_sheet = workbook[sheet]
        # Verifica si la hoja est� oculta
        if current_sheet.sheet_state == 'hidden':
            # Elimina la hoja
            del workbook[sheet]

    # Guarda los cambios en el archivo Excel
    workbook.save(file)
    workbook.close()

# def recalc_forms_and_del_hidde_sheets(file):
#     excel_app = xlwings.App(visible=False)
#     excel_book = excel_app.books.open(file)
#     for sheet in excel_book.sheets:
#         if sheet.visible != -1:
#             sheet.delete()
#     excel_book.save()
#     excel_book.close()
#     excel_app.quit()   

def search_key_words(text,key_word):
    text = unidecode(text)
    special_keywords = {
        "bcb": "banco central bolivia",
        "tc": "tipo cambio",
        "ipc": "indice precios consumidor",
        "mn": "moneda nacional",
        "me": "moneda extranjera",
        "pib": "producto interno bruto"
    }
    
    key_words = key_word.split(' ')

    # Iterate through keywords and search in text
    for k in key_words:
        regex = re.compile(r'\b' + re.escape(k), re.IGNORECASE|re.UNICODE)
        
        is_in_text = regex.search(text)

        # If keyword not found, check special keywords
        if not is_in_text:
            if k in special_keywords:
                for j in special_keywords[k].split(' '):
                    
                    regex = re.compile(r'\b' + re.escape(j), re.IGNORECASE|re.UNICODE)
                    
                    if not regex.search(text):
                        return False
            else:
                return False
    return True

# convert a windows path to a linux path
def convert_win_path(path_win, add_dir=""):
    path_unix = path_win.replace (ntpath.sep, posixpath.sep)
    #path_unix = path_unix.replace("//10.0.0.9/spim/","/media/spim_1/")+add_dir
    #path_unix = path_unix.replace("//10.0.0.9/SPIM/","/media/spim_1/")+add_dir
    path_unix = path_unix.replace('\\\\','\\')
    path_unix = path_unix.replace("//10.0.0.9/spim/","/media/spim_10009/")+add_dir
    path_unix = path_unix.replace("//10.0.0.9/SPIM/","/media/spim_10009/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/spim/","/media/datax/Local_Disk_B/spim/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/data_process/","/media/datax/Local_Disk_B/data_process/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/downloaded_files/","/media/datax/Local_Disk_B/downloaded_files/")+add_dir
    return path_unix

# convert a linux path to a windows path
def convert_unix_path(path_unix, add_dir=""):
    path_win = path_unix.replace(posixpath.sep, ntpath.sep)
    #path_win = ''.join(path_win)
    path_win = path_win.replace("\\","\\\\")
    path_win = path_win.replace("\\\\media\\\\spim_10009","\\\\\\\\10.0.0.9\\\\spim")+add_dir
    path_win = path_win.replace("\\home\\datax-ubuntu\\","\\\\10.0.0.9\\")+add_dir
    path_win = path_win.replace("\\\\media\\\\datax\\\\Local_Disk_B\\\\spim","\\\\\\\\10.0.0.12\\\\spim")+add_dir
    path_win = path_win.replace("\\\\media\\\\datax\\\\Local_Disk_B\\\\data_process","\\\\\\\\10.0.0.12\\\\data_process")+add_dir
    path_win = path_win.replace("\\\\media\\\\datax\\\\Local_Disk_B\\\\downloaded_files","\\\\\\\\10.0.0.12\\\\downloaded_files")+add_dir                   
    return path_win    

def get_departamento_abr(dep):
    dep = dep.strip().lower()
    departamentos_dict = {
    "la paz": "lp",
    "santa cruz": "sc",
    "cochabamba": "cb",
    "oruro": "or",
    "potosi": "pt",
    "chuquisaca": "ch",
    "tarija": "tj",
    "beni": "bn",
    "pando": "pd"
}
    return departamentos_dict[dep]

def register_log(logger,execution_type,duration, num=0,files=[],main_url='-'):
    reference_datetime = datetime(2000, 1, 1, 0, 0, 0)
    duration_datatime = reference_datetime + duration
    execution_types = {
        
        "1":"Download",
        "2":"Review Only",
        "3":"Download Review",
    }
    if execution_type in ["2","3"]:
        num=num+1
        log_dic = {
            "num": num,
            "downloaded_to": "-",
            "execution_type": execution_types[execution_type],
            "duration":duration_datatime.strftime("%H:%M:%S"),
            "spim_code": "-",
            "main_url":main_url,
            "url": "-"
        }
        logger.info("",extra=log_dic)
    else:
        for file in files:
            num=num+1
            log_dic = {
            "num": num,
            "downloaded_to": file["updated_to"],
            "execution_type": execution_types[execution_type],
            "duration":duration_datatime.strftime("%H:%M:%S"),
            "spim_code": "-",
            "main_url":main_url,
            "url": file["download_url"]
        }
            logger.info("",extra=log_dic)
    
def execution_log(path,execution_date, key_words,file_code, file_name, publication_frequency, execution_schedule, spim_code, execution_type,duration, num=0,files=[],main_url='-'):
    """
    This function creates and updates an execution log file for a specific scraping process.

    Args:
        path (str): The path where the log file will be saved.
        key_words (str): Keywords to identify the log file (with underscores replacing spaces).
        file_code (str): Code associated with the robot code.
        file_name (str): Name of the scraped file.
        publication_frequency (str): How often the file is updated.
        execution_schedule (str): When the scraping process is scheduled to run.
        spim_code (str): SPIM codes with the robot is linked.
        execution_type (str): Type of execution (Download, Review Only, Download Review).
        duration (str): Time it took to execute the scraping process.
        files (list, optional): List of dictionaries containing downloaded file information (updated_to and download_url keys). Defaults to [].
        main_url (str, optional): Base URL used for scraping (defaults to '-').
  """
    log_file = os.path.join(path,f"{key_words} Execution Log.txt")
    num = 0
    if not os.path.exists(log_file):
        with open(log_file, 'w') as f:
            f.write(f"File Code: {file_code}\n")
            f.write(f"File Name: {file_name}\n")
            f.write(f"Update Frecuency: {publication_frequency}\n")
            f.write(f"Execution Schedule: {execution_schedule}\n")
            f.write(f"Url Base: {main_url}\n")
            f.write(f"Spim Code: {spim_code}\n")
            f.write("\nExecution Log\n-------------\n")
            f.write("Nro   Execution Date      Downloaded To Duration Execution Type  Download Url\n")
        
    else:
        with open(log_file, 'r') as f:
            lines = f.readlines()

        while lines[-1].strip() == '':
            if len(lines)==0:
                raise Exception("Log file empty")
            lines = lines[:-1]

        with open(log_file, 'w') as f:
            f.writelines(lines)
            
        last_line = lines[-1].split()
        num = int(last_line[0]) if last_line[0].isdigit() else 0
        
    
    # today = datetime.today()

    execution_types = {
        
        "1":"Download",
        "2":"Review Only",
        "3":"Download Review",
        "4":"Url Broken"
    }
    with open(log_file, 'a') as f:

        if execution_type in ["2","3","4"]:
            num=num+1
            f.write(f"{str(num).ljust(5)} {execution_date} {'-'.ljust(13)} {duration} {execution_types[execution_type].ljust(15)} -\n")
        else:
            for file in files:
                num=num+1
                f.write(f"{str(num).ljust(5)} {execution_date} {file['updated_to'].ljust(13)} {duration} {execution_types[execution_type].ljust(15)} {file['download_url']}\n")

def read_excel(file_name:str,sheet_name=0,headers=None)->pd.DataFrame:
    try:
        return pd.read_excel(file_name,sheet_name=sheet_name,header=headers)
    except ValueError:
        return pd.read_excel(file_name,sheet_name=sheet_name,header=headers,engine='xlrd')