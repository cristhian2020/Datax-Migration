import os
import shutil
import re
import fitz
import ntpath
import posixpath
import numpy as np
import pandas as pd
import pandas.api.types as ptypes
from typing import Tuple,List
from unidecode import unidecode
# from rapidfuzz import fuzz, process
# from models.conversion.tools.text_normalization import Text_Normalization
from download_tools import createDirectoryStruct, convert_unix_path, convert_win_path, month_abr_to_number, month_to_number, last_day_month, format_date

def identations(row, dictionary):
    if row in dictionary:
        indent = '0'
        if dictionary[row]>50:
            indent = '2'
        elif dictionary[row]>40:
            indent = '1'
        return indent + row
    else:
        return row
    
def search_key_words(text, key_words, exact=False):
    text = unidecode(text)    
    
    splited_text = key_words.split(' ')

    key_words_tokens = []
    ignored_terms = []

    for word in splited_text:
        if word.startswith("~"):
            ignored_terms.append(word[1:])
        else:
            key_words_tokens.append(word)
    
    if exact:
        pattern =  r"\b" + r"\b\s+\b".join(key_words_tokens) + r"\b"
    else:
        pattern = r"\b" + r".*\b".join(key_words_tokens) 
    
    pattern = rf'(?s)^(?!.*\b{ignored_terms[0]})' + pattern if ignored_terms else r"(?s)"  + pattern    
    regex = re.compile(pattern, re.IGNORECASE|re.UNICODE)    
    if regex.search(text):
        return True
    else:
        return False

def search_key_words_withouth_whitespaces(text, key_words):
    text = re.sub(r'\s+','',text)
    text = unidecode(text)    
    
    key_words_tokens = key_words.split(' ')
    
    pattern = r".*".join(key_words_tokens)     
    
    regex = re.compile(pattern, re.IGNORECASE|re.UNICODE)    
    if regex.search(text):
        return True
    else:
        return False

def organize_and_copy_files_by_status(files,date,base_path,publication_frequency,format='%Y-%m-%d_%H-%M-%S'):
    base_path = createDirectoryStruct(file_date=date,base_path=base_path,publication_frequency=publication_frequency)
    directories = []
    for f in files:        
        f["file_path"] = convert_win_path(f["file_path"].replace("\\\\","\\"))
        
        file_name = os.path.basename(f["file_path"])
        if f['status'] is None or f['status'] in ['successful_conversion','no_updates']:
            continue
        dir_file = os.path.join(base_path,f"{date.strftime(format)}__{f['status']}")
        os.makedirs(dir_file,exist_ok=True)
        shutil.copy(src=f["file_path"],dst=os.path.join(dir_file,file_name))
        directories.append(dir_file)
    if directories:
        directories = set(directories)
        directories = [{"path":convert_unix_path(item),"status":item.split('__')[-1]} for item in directories]
    return directories

# def verify_titles(template_df, data_df):
#     titles_template = [template_df[column].iloc[0] for column in template_df.columns if str(column).startswith("titulo")]
#     titles_data = [data_df[column].iloc[0] for column in data_df.columns if str(column).startswith("titulo")]

#     # Check if the number of titles in the template and data match
#     if len(titles_template)!=len(titles_data):    
#         raise ValueError("The number of titles in the template and data does not match.")
    
#     # Iterate through each title in the template and compare with the corresponding title in the data
#     for i, template_title in enumerate(titles_template):
#         if not template_title or str(template_title) == 'nan':            
#             continue   
#         similarity = fuzz.ratio(str(template_title).lower(), str(titles_data[i]).lower())

#         # Raise an error if the similarity is below the acceptable threshold
#         if similarity < 75:
#             raise ValueError(f"Title mismatch detected: Template title {template_title} does not match New report title {titles_data[i]}.")   
    
    
def verify_frecuency(template_df, data_df):
    template_dates = template_df['fecha'].replace('-',pd.NA).dropna().apply(lambda x: format_date(str(x))).sort_values(ascending=True).unique().tolist()
    data_dates =data_df['fecha'].replace('-',pd.NA).dropna().apply(lambda x: format_date(str(x))).sort_values(ascending=True).unique().tolist()
    
    if len(data_dates)==1:
        data_dates.append(data_dates[0])    
    if len(template_dates)==1:
        template_dates.append(template_dates[0])    
    
    frecuency_template = template_dates[-1] - template_dates[-2]
    frecuency_data = abs(data_dates[-1] - data_dates[-2])    
    if abs(frecuency_data.days-frecuency_template.days) >3:
        raise ValueError(f"Date frequency mismatch.")

def search_value(text,label):
    text = unidecode(text)
    pattern = r'\b'+label+r'\s*'+':'+r'\s*'+r'\b([\w.,]+)\b'
    regex = re.compile(pattern, re.IGNORECASE|re.UNICODE)    
    if regex.search(text):
        return regex.search(text).group(1)
    else:
        return False

def extract_report_df(df,pivot_keywords, exact=False, top_gap=0):    
    pivot = None
    for i,column in enumerate(df.columns):
        if exact:
            matches = df.loc[df[column].apply(lambda x: str(x).lower().strip() ==pivot_keywords), column]
        else:
            matches = df.loc[df[column].apply(lambda x: search_key_words(text=str(x), key_words=pivot_keywords)), column]
        matches = matches.dropna()

        if not matches.empty:
            indices = matches.index
            pivot = (i, indices[0]-top_gap)
            break
    if not pivot:
        raise ValueError("The pivot could not be found in the file.")
    titles, splited_df = df.loc[:pivot[1]-1], df.loc[pivot[1]:,df.columns[pivot[0]:]]
    titles = titles.dropna(how='all')
    titles = titles.agg(lambda x: " ".join(x.dropna()), axis=1).to_list()    
    
    return splited_df,titles

def get_date(text):
    date = text.split("_")
    if not date[0]:
        return date[1]
    date[1] = month_to_number(date[1]) if month_to_number(date[1]) else month_abr_to_number(date[1])
    if not date[1]:
        return date[0]
    day = last_day_month(year=int(date[0]),month=date[1])
    return f"{date[0]}-{date[1]:02}-{day}"

def get_col_date(col):
    if pd.isna(col):
        return col
    quarters = {
        "i": 3,
        "ii": 6,
        "iii": 9,
        "iv": 12,
    }
    re_year = r'(\d{4})'
    re_month = r'((?:enero|febrero|marzo|abril|mayo|junio|julio|agosto|septiembre|octubre|noviembre|diciembre|ene|feb|mar|abr|may|jun|jul|ago|sep|oct|nov|dic|jan|apr|aug|dec|set))'
    re_quarter = r'(\w+)\strim|trimestre'
    re_day = r'(\d{1,2})\D+\s*'
    year = re.search(re_year, col)
    month_string = re.search(re_month, col, re.IGNORECASE)
    quarter = re.search(re_quarter,col,re.IGNORECASE)
    day = re.search(re_day,col,re.IGNORECASE)
    if quarter:        
        month = quarters[quarter.group(1).lower()]
    elif month_string:
        month_string = month_string.group(1)
        month = month_abr_to_number(month_string) if month_abr_to_number(month_string) else month_to_number(month_string)
    elif year:
        month = 12
    else:
        return col    
    year = year.group(1)
    if day:
        day = day.group(1)
    else:
        day = last_day_month(year=int(year), month=month)
    return f"{year}-{month:02}-{day}"

def get_pdf_report_page(pdf, key_words, num_caracteres=150,page_number=0):
    page_number = int(page_number)
    def extract_text(page, num_chars):
        """Extracts text from the page up to num_chars, or all if specified."""
        text = page.extract_text()
        return text if num_chars == 'ALL' else text[:num_chars]
   
    page_number = max(page_number - 1, 0)
    
    initial_text = extract_text(pdf.pages[page_number], num_caracteres)
    if search_key_words(text=initial_text, key_words=key_words):
        return pdf.pages[page_number]
    
    for page in pdf.pages:
        text = extract_text(page, num_caracteres)
        if search_key_words(text=text, key_words=key_words):
            return page
    
    raise ValueError("The report could not be found in the file.")

def insert_metadata(dataframe, titles, file_name):
    for i,title in enumerate(reversed(titles)):
        dataframe.insert(0,column=f"titulo{len(titles)-i}",value=title)
    
    dataframe.insert(0,column='file',value=file_name)
    
    return dataframe

# def isLevel(nv,text,percentage_simliraty=90):    
#     nv = [Text_Normalization.get_srch_value(str(i)) for i in nv]    
#     text = Text_Normalization.get_srch_value(str(text))
#     result = process.extractOne(text,nv)
#     similarity = result[1]
    
#     return similarity>percentage_simliraty

# def verify_levels(template_df, data_df,columns_to_review,percentage_simliraty=90):
#     template_df = template_df.dropna(how='all',axis=1)
#     print(f"Columns identified for level verification: {columns_to_review}")
#     for column in columns_to_review:
#         nv = template_df[column].dropna().unique()
#         nv_mask = data_df.loc[:,column].apply(lambda x: isLevel(nv=nv,text=x,percentage_simliraty=percentage_simliraty))
#         nv_df = data_df.loc[~nv_mask,column].dropna()
#         if not nv_df.empty:
#             print(f"Error: The following values in column '{column}' do not match expected levels:")
#             print(nv_df)
#             raise ValueError(f"Extraction error: Column '{column}' contains values that do not match the expected levels.")
    
#     print("Level verification completed successfully.")

def verify_values(data_df):
    numeric_column = 'valor' if 'valor' in data_df.columns.to_list() else data_df.columns[-1]    
    values = data_df[numeric_column].dropna()
    numeric_mask = pd.to_numeric(values.replace(r'\s+','',regex=True).apply(lambda x: re.sub(r'[.(),%]', '', str(x)).replace('-','0')),errors='coerce').notna()

    no_numeric_df = values[~numeric_mask]
    if not no_numeric_df.empty:
        print("Error: The following values in the 'valor' column are non-numeric or invalid:")
        print(no_numeric_df)
        raise Exception("Value verification failed: 'valor' column contains non-numeric or invalid values.")
    
    print("Value verification completed successfully. All values in 'valor' column are numeric.")

def get_xlsx_report_dataframe(file_path:str, key_words:str, page_number:int=1, sheets_to_exclude:List[int]=[]) -> Tuple[pd.DataFrame,int]:
    tables = pd.read_excel(file_path,sheet_name=None,header=None)
    page_number = 0 if (n:=page_number-1)<0 or n>len(tables) else n

    if page_number != 0:
        page_sheet_name = list(tables.keys())[page_number]
        search_mask = tables[page_sheet_name].astype(str).map(lambda x: search_key_words(text=x,key_words=key_words)).any(axis=1)
        search_df = tables[page_sheet_name].loc[search_mask]
        if not search_df.empty:
            return (tables[page_sheet_name],page_number+1)

    for i,sheet_name in enumerate(tables):
        if i in sheets_to_exclude:
            continue       
        search_mask = tables[sheet_name].astype(str).map(lambda x: search_key_words(text=x,key_words=key_words)).any(axis=1)
        search_df = tables[sheet_name].loc[search_mask]
        if not search_df.empty:
            return (tables[sheet_name],i+1)
    return

def get_xlsx_report_dataframe_full(file_path:str, key_words:str, page_number:int=1, sheets_to_exclude:List[int]=[]) -> Tuple[pd.DataFrame,int]:
    tables = pd.read_excel(file_path,sheet_name=None,header=None)
    page_number = 0 if (n:=page_number-1)<0 or n>len(tables) else n
    
    if page_number != 0:
        page_sheet_name = list(tables.keys())[page_number]        
        df = tables[page_sheet_name].apply(lambda x: " ".join(x.dropna().astype(str)))
        search_mask = df.astype(str).map(lambda x: search_key_words(text=x,key_words=key_words))#.any(axis=1)
        search_df = df.loc[search_mask]
        print(search_df,search_df.empty)
        if not search_df.empty:
            return (tables[page_sheet_name],page_number+1)

    for i,sheet_name in enumerate(tables):
        if i in sheets_to_exclude:
            continue
        df = tables[sheet_name].dropna(how='all')
        df = df.apply(lambda x: " ".join(x.dropna().astype(str)))      
        search_mask = df.astype(str).map(lambda x: search_key_words(text=x,key_words=key_words))#.any(axis=1)
        search_df = df.loc[search_mask]
        if not search_df.empty:
            return (tables[sheet_name],i+1)
    return

def convert_win_path(path_win, add_dir=""):

    path_win = path_win.replace('\\\\','\\')
    path_unix = path_win.replace(ntpath.sep, posixpath.sep)
    path_unix = '//' + '/'.join([i for i in path_unix.split('/') if i])
    path_unix = path_unix.replace("//10.0.0.9/spim/","/media/spim_10009/")+add_dir
    path_unix = path_unix.replace("//10.0.0.9/SPIM/","/media/spim_10009/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/spim/","/media/datax/Local_Disk_B/spim/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/data_process/","/media/datax/Local_Disk_B/data_process/")+add_dir
    path_unix = path_unix.replace("//10.0.0.12/downloaded_files/","/media/datax/Local_Disk_B/downloaded_files/")+add_dir
    return path_unix

# convert a linux path to a windows path
def convert_unix_path(path_unix, add_dir=""):
    path_unix = path_unix.replace("/media/spim_10009/","//10.0.0.9/spim/")+add_dir
    path_unix = path_unix.replace("/media/spim_10009/","//10.0.0.9/SPIM/")+add_dir
    path_unix = path_unix.replace("/media/datax/Local_Disk_B/spim/","//10.0.0.12/spim/")+add_dir
    path_unix = path_unix.replace("/media/datax/Local_Disk_B/data_process/","//10.0.0.12/data_process/")+add_dir
    path_unix = path_unix.replace("/media/datax/Local_Disk_B/downloaded_files/","//10.0.0.12/downloaded_files/")+add_dir
    path_win = path_unix.replace(posixpath.sep, ntpath.sep)
    
    return path_win

def extract_pdf_table_fitz(file:str,page:int)->pd.DataFrame:
    with fitz.open(file) as pdf:
        page = pdf[page]
        text = page.get_text('blocks')

    lines = []
    for block in text:        
        line = [re.sub(r'\s+',' ',cell) for cell in block[4].split('\n')]
        line = [cell for cell in line if cell and cell != ' ']
        lines.append(line)
    
    max_length = max(len(line) for line in lines)
    final_lines = [ [np.nan] * (max_length - len(line)) + line for line in lines]
    
    df = pd.DataFrame(final_lines)
        
    return df

def to_numeric_datax(serie: pd.Series, decimal_separator: str) -> pd.Series:
    """
    Converts a pandas Series with numeric values to actual numeric types.

    Parameters:
    ----------
    serie : pd.Series
        A pandas Series containing numeric values as strings. These values might include
        thousand separators, decimal points, percentage signs, or negative numbers in parentheses.

    decimal_separator : str
        Specifies the decimal separator used in the input data.
        Accepted values are '.' for dot or ',' for comma.

    Returns:
    -------
    pd.Series
        A pandas Series of numeric values (floats or integers). Non-convertible entries are set to NaN.

    Raises:
    ------
    ValueError
        If the provided decimal_separator is not '.' or ','.
    TypeError
        If the input is not a pandas Series.
    """
    if ptypes.is_numeric_dtype(serie):
        return serie
    # Validate input type
    if not isinstance(serie, pd.Series):
        raise TypeError("Input must be a pandas Series.")

    # Validate decimal separator
    decimal_separator = decimal_separator.strip()
    if decimal_separator not in ['.', ',']:
        raise ValueError("Invalid decimal separator. Use '.' or ','.")
    
    # Convert series to string for safe manipulation
    serie = serie.astype(str)

    # Remove thousand separators and adjust decimal point
    if decimal_separator == '.':
        # Remove commas (thousands separator)
        serie = serie.str.replace(r',', '', regex=True)
    else:
        # Remove dots (thousands separator) and replace commas with dots (decimal separator)
        serie = serie.str.replace(r'\.', '', regex=True).str.replace(r',', '.', regex=True)

    # Clean up unwanted characters like spaces, percentages, and parentheses for negatives
    serie = serie.str.replace(r'[)\s+%]', '', regex=True).str.replace(r'\(', '-', regex=True)

    # Convert cleaned string to numeric values, coercing errors to NaN
    return pd.to_numeric(serie, errors='coerce')

def is_all_string_or_nan(dataframe:pd.DataFrame):
    columns_to_check = dataframe.columns[:-1]

    violating_columns = [
        col for col in columns_to_check
        if not dataframe[col].apply(lambda x: isinstance(x, str) or pd.isna(x)).all()
    ]
    
    if violating_columns:
        print(f"The following columns do NOT follow the rule (must be string or NaN): {violating_columns}")
        return False
    else:
        print("All checked columns comply with the rule (only strings or NaN).")

    return True