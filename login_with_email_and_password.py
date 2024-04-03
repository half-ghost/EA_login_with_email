import asyncio
import json
import os
import random
import re

import aiohttp
from lxml import html

FILE_PATH = os.path.dirname(__file__)


email = ""
password = ""
start_url = r"https://accounts.ea.com/connect/auth?client_id=sparta-companion-web&response_type=code&display=web2/login&locale=en_US&redirect_uri=https%3A%2F%2Fcompanion-api.battlefield.com%2Fcompanion%2Fsso%3Fprotocol%3Dhttps"

def write_to_file(data, *args):
    with open(os.path.join(FILE_PATH, *args), "w", encoding="utf-8") as f:
        f.write(data)


def read_from_file(*args):
    if os.path.exists(os.path.join(FILE_PATH, *args)):
        with open(os.path.join(FILE_PATH, *args), "r", encoding="utf-8") as f:
            return f.read()
    else:
        return ""

# cid值的生成算法
def random_string(length=32):
    characters = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghiklmnopqrstuvwxyz"
    return "".join(random.choice(characters) for _ in range(length))


async def login(email, password):
    session = aiohttp.ClientSession()
    # 设定accep-language接受中文语言,以防出现未知的问题
    session.headers.update(
        {"Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8,en-GB;q=0.7,en-US;q=0.6"}
    )
    # 读取存储的cookie文件,如果上次登录过则存在"osc"和"_nx_mpcid"两个值
    old_cookie = json.loads(read_from_file("cookie.json"))
    # 更新session的cookie,加入"osc"和"_nx_mpcid",使登录可以不用邮箱验证码
    if len(old_cookie) != 0:
        session.cookie_jar.update_cookies(old_cookie)
    # 第一次请求的url,请求后会返回一个带有"execution"和"initref"查询参数的登录页面
    resp1 = await session.get(start_url)

    # 将账号密码以及cid算法和其他参数一起构建发送请求
    request_data1 = {
        "email": email,
        "regionCode": "CN",
        "phoneNumber": "",
        "password": password,
        "_eventId": "submit",
        "cid": f"{random_string()},{random_string()}",
        "showAgeUp": "true",
        "thirdPartyCaptchaResponse": "",
        "loginMethod": "emailPassword",
        "_rememberMe": "on",
        "rememberMe": "on",
    }
    url_s1 = resp1.url
    resp2 = await session.post(url_s1, data=request_data1)

    # 解析响应页面内容,查找是否存在打码邮箱元素
    tree = html.fromstring(await resp2.text())
    email_code_element = tree.xpath(
        '//input[@type="radio" and @name="_codeType" and @value="EMAIL"]'
    )
    # 查找页面是否存在接收新的隐私条款按钮元素
    readAccept_element = tree.xpath(
        '//input[@type="checkbox" and @id="readAccept" and @name="readAccept"]'
    )
    # 如果页面存在打码邮箱元素则说明需要发送邮箱验证码,否则直接拿到页面上的重定向链接
    if len(email_code_element) != 0:
        print("需要邮箱验证码")
        email_code = email_code_element[0].get("id")
        request_data2 = {
            "codeType": "EMAIL",
            "maskedDestination": email_code.split(":")[-1],
            "_codeType": "EMAIL",
            "_eventId": "submit",
        }
        # 拿到发送邮箱验证码之后的网页url
        url_s2 = resp2.url
        resp3 = await session.post(url_s2, data=request_data2)

        url_s3 = resp3.url
        # 将收到的邮箱验证码填入,并构建请求参数
        captcha_code = input("直接在此处填入邮箱验证码:")
        request_data3 = {
            "oneTimeCode": str(captcha_code),
            "_trustThisDevice": "on",
            "trustThisDevice": "on",
            "_eventId": "submit",
        }
        # 构建完发送请求,相当于在网页上写入验证码并提交
        resp4 = await session.post(url_s3, data=request_data3)
        cookie = resp4.cookies
        # 储存验证码通过后的cookie,"osc"和"_nx_mpcid",用于保存登录过的状态
        write_to_file(
            json.dumps({k: cookie[k].value for k in cookie}, ensure_ascii=False),
            "cookie.json",
        )
        # 向提交验证码后重定向的网页发起请求
        resp4_text = await resp4.text()
        redirect_url = re.findall(
            'window.location="(.*?)";', (resp4_text.replace(" ", ""))
        )[0]
    # 如果存在接收新的隐私条款按钮则构造新的请求参数发送请求
    elif len(readAccept_element) != 0:
        print("需要同意新策略")
        request_data2 = {"_readAccept": "on", "readAccept": "on", "_eventId": "accept"}
        url_s2 = resp2.url
        resp3 = await session.post(url_s2, data=request_data2)
        resp3_text = await resp3.text()
        redirect_url = re.findall(
            'window.location="(.*?)";', (resp3_text.replace(" ", ""))
        )[0]
    else:
        resp2_text = await resp2.text()
        redirect_url = re.findall(
            'window.location="(.*?)";', (resp2_text.replace(" ", ""))
        )[0]
    # 此处禁止重定向拿到的cookie是remid和sid,允许则是gateway_session
    resp5 = await session.get(redirect_url, allow_redirects=False)
    # resp5的cookies是remid和sid
    print(resp5.cookies)
    resp6 = await session.get(resp5.headers["Location"])
    # resp6的cookies是gateway_session
    print(resp6.cookies)
    await session.close()
