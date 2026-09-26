import os
import json
import requests
import logging
from urllib3.exceptions import InsecureRequestWarning
from urllib.parse import quote
from dotenv import load_dotenv

# 同步日志（复用后端 logger 配置）
_api_logger = logging.getLogger("sync")

REQUESTS_VERIFY = os.getenv("REQUESTS_VERIFY", "true").lower() == "true"
TIMEOUT = (10, 30)  # (connect, read) seconds

if not REQUESTS_VERIFY:
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


def _credential_shape() -> str:
    """只记凭证是否存在和长度，不记内容。"""

    def one(name: str, value: str | None) -> str:
        if not value:
            return f"{name}=空"
        return f"{name}=长度{len(value)}"

    return " ".join([
        one("openid", OPENID),
        one("access_token", ACCESS_TOKEN),
        one("refresh_token", REFRESH_TOKEN),
        one("authorization", AUTHORIZATION_TOKEN),
    ])


def _redact(text: str) -> str:
    redacted = text
    for secret in (ACCESS_TOKEN, REFRESH_TOKEN, AUTHORIZATION_TOKEN, OPENID):
        if secret and len(secret) >= 6:
            redacted = redacted.replace(secret, "***")
    redacted = redacted.replace("\n", " ")
    if len(redacted) > 300:
        return redacted[:300] + "…"
    return redacted


def direct_login():
    """Refreshes the AUTHORIZATION_TOKEN using ACCESS_TOKEN and REFRESH_TOKEN."""
    global AUTHORIZATION_TOKEN
    if not ACCESS_TOKEN or not REFRESH_TOKEN:
        _api_logger.warning("缺少 ACCESS_TOKEN 或 REFRESH_TOKEN。%s", _credential_shape())
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
        _api_logger.info(
            "正在刷新登录会话... %s %s",
            "走代理" if PROXIES else "直连",
            _credential_shape(),
        )
        response = requests.post(DIRECT_LOGIN_URL, json=payload, headers=headers, proxies=PROXIES, verify=REQUESTS_VERIFY, timeout=TIMEOUT)
        response.raise_for_status()
        res_json = response.json()
        if res_json.get("code") == 0:
            new_token = res_json["data"]["fd_token"]
            AUTHORIZATION_TOKEN = new_token
            _api_logger.info("登录会话刷新成功，authorization=长度%s", len(new_token or ""))
            return True
        _api_logger.warning(
            "登录刷新失败: http=%s code=%s msg=%s 响应字段=%s %s",
            response.status_code,
            res_json.get("code"),
            res_json.get("msg"),
            ",".join(sorted(str(key) for key in res_json.keys())),
            _credential_shape(),
        )
        return False
    except Exception as e:
        resp = getattr(e, "response", None)
        status = getattr(resp, "status_code", None)
        body = _redact(getattr(resp, "text", "") or "") if resp is not None else ""
        _api_logger.error("登录刷新请求失败: %s http=%s body=%s %s", e, status, body, _credential_shape())
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
        response = requests.post(GATEWAY_URL, data=body, headers=headers, proxies=PROXIES, verify=REQUESTS_VERIFY, timeout=TIMEOUT)
        res_json = response.json()
        
        # Handle expired session
        if res_json.get("code") == 4001 and retry:
            _api_logger.warning("登录会话过期，正在自动刷新... path=%s", req_path)
            if direct_login():
                return gateway_request(req_path, req_param, req_type=req_type, retry=False)
            _api_logger.warning("登录刷新未成功，不再重试 path=%s", req_path)

        if res_json.get("code") != 0:
            _api_logger.warning(
                "API %s 错误: http=%s code=%s msg=%s",
                req_path,
                response.status_code,
                res_json.get("code"),
                res_json.get("msg"),
            )
            return None
        return res_json.get("data")
    except Exception as e:
        _api_logger.error(f"请求失败 {req_path}: {e}")
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
        response = requests.get(url, proxies=PROXIES, verify=REQUESTS_VERIFY, timeout=TIMEOUT)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        _api_logger.error(f"获取 {baseid} 基础信息失败: {e}")
        return None
