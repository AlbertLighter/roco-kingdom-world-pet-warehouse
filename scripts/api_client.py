import os
import json
import requests
from urllib3.exceptions import InsecureRequestWarning
from urllib.parse import quote
from dotenv import load_dotenv

# Suppress insecure request warnings when using a proxy
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

load_dotenv()

X_MCUBE_ACT_ID = os.getenv("X_MCUBE_ACT_ID", "E80EH8LJ")
AUTHORIZATION_TOKEN = os.getenv("AUTHORIZATION_TOKEN")
OPENID = os.getenv("OPENID")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
REFRESH_TOKEN = os.getenv("REFRESH_TOKEN")
APPID = os.getenv("APPID", "102802421")
HTTP_PROXY = os.getenv("HTTP_PROXY")
HTTPS_PROXY = os.getenv("HTTPS_PROXY")

PROXIES = {
    "http": HTTP_PROXY,
    "https": HTTPS_PROXY
} if HTTP_PROXY or HTTPS_PROXY else None

GATEWAY_URL = f"https://morefun.game.qq.com/gw2/gateway/v1/?X-Mcube-Act-Id={X_MCUBE_ACT_ID}"
DIRECT_LOGIN_URL = "https://morefun.game.qq.com/oauth/v1/direct-login"
BASE_INFO_URL_TEMPLATE = "https://rocom.qq.com/cp/rocom_game_manager_json/prod/sprite/base_info/{baseid}.json"

def direct_login():
    """Refreshes the AUTHORIZATION_TOKEN using ACCESS_TOKEN and REFRESH_TOKEN."""
    global AUTHORIZATION_TOKEN
    if not ACCESS_TOKEN or not REFRESH_TOKEN:
        print("Missing ACCESS_TOKEN or REFRESH_TOKEN in environment.")
        return False
        
    payload = {
        "account_type": "qq",
        "appid": APPID,
        "openid": OPENID,
        "access_token": ACCESS_TOKEN,
        "refresh_token": REFRESH_TOKEN
    }
    headers = {
        "content-type": "application/json",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Mac MacWechat/WMPF MacWechat/3.8.7(0x13080712) UnifiedPCMacWechat(0xf2641701) XWEB/18788"
    }
    
    try:
        print("Attempting to refresh login session...")
        response = requests.post(DIRECT_LOGIN_URL, json=payload, headers=headers, proxies=PROXIES, verify=False)
        response.raise_for_status()
        res_json = response.json()
        if res_json.get("code") == 0:
            new_token = res_json["data"]["fd_token"]
            AUTHORIZATION_TOKEN = new_token
            print("Login session refreshed successfully.")
            return True
        else:
            print(f"Login refresh failed: {res_json.get('msg')}")
            return False
    except Exception as e:
        print(f"Login refresh request failed: {e}")
        return False

def gateway_request(req_path, req_param, req_type="POST", retry=True):
    payload = {
        "account_type": "qq",
        "openid": OPENID,
        "area_id": 2,
        "plat_id": 1,
        "biz_code": "rocom",
        "act_id": X_MCUBE_ACT_ID,
        "server_type": 1,
        "req_path": req_path,
        "req_type": req_type,
        "req_param": req_param,
        "app_name": "102802421"
    }
    data_str = json.dumps(payload, separators=(',', ':'))
    body = f"data={quote(data_str)}"
    
    headers = {
        "authorization": AUTHORIZATION_TOKEN,
        "content-type": "application/x-www-form-urlencoded",
        "user-agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36 MicroMessenger/7.0.20.1781(0x6700143B) NetType/WIFI MiniProgramEnv/Mac MacWechat/WMPF MacWechat/3.8.7(0x13080712) UnifiedPCMacWechat(0xf2641701) XWEB/18788"
    }
    
    try:
        response = requests.post(GATEWAY_URL, data=body, headers=headers, proxies=PROXIES, verify=False)
        res_json = response.json()
        
        # Handle expired session
        if res_json.get("code") == 4001 and retry:
            print("Login session expired. Attempting auto-refresh...")
            if direct_login():
                return gateway_request(req_path, req_param, req_type=req_type, retry=False)
                
        if res_json.get("code") != 0:
            print(f"Error in API {req_path}: {res_json.get('msg')}")
            if response.status_code != 200:
                print(f"HTTP Status: {response.status_code}")
            return None
        return res_json.get("data")
    except Exception as e:
        print(f"Request failed: {e}")
        return None

def fetch_user_info():
    """Fetches user information (API endpoint /api/user/info)."""
    return gateway_request("/api/user/info", {
        "targetUserUin": "",
        "targetRoleID": "",
        "settingType": []
    })

def fetch_refresh_time():
    """Fetches pet refresh time (API endpoint /api/pet/getRefreshTime)."""
    return gateway_request("/api/pet/getRefreshTime", {}, req_type="GET")

def fetch_base_info(baseid):
    url = BASE_INFO_URL_TEMPLATE.format(baseid=baseid)
    try:
        response = requests.get(url, proxies=PROXIES, verify=False)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"Failed to fetch base info for {baseid}: {e}")
        return None
