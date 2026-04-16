"""
新闻资讯采集
从金十数据、金十期货、新浪财经、财联社四个网站抓取新闻资讯，并存入数据库。
rewrote by 鲁炎 on 2024-05-27
"""
from datetime import datetime
import time
import json
import requests
import pymysql
import dingtalk

dbase = {
    'host': "xxx",
    'port': 3306,
    'user': "root",
    'pwd': "xxx",
    'name': "eco_news",
}


def get_data(sql_str):  # 从数据库调取数据，SELECT
    db = pymysql.connect(host=dbase['host'],
                         port=dbase['port'],
                         user=dbase['user'],
                         password=dbase['pwd'],
                         database=dbase['name'])
    cursor = db.cursor()
    try:
        cursor.execute(sql_str)
        results = cursor.fetchall()
    except Exception as e:
        results = None
    db.close()
    return results


def set_db(sql_str):  # 对数据库进行操作，INSERT REPLACE UPDATE DELETE
    sql_str = sql_str[:-1] + ';'
    if len(sql_str) > 27:
        db = pymysql.connect(host=dbase['host'],
                             port=dbase['port'],
                             user=dbase['user'],
                             password=dbase['pwd'],
                             database=dbase['name'])
        cursor = db.cursor()
        try:
            cursor.execute(sql_str)
            db.commit()
            flag = True
        except Exception as e:
            # 发生错误时回滚
            db.rollback()
            flag = False
        db.close()
        return flag


def get_jin10(last_time):
    # 根据当前时间，生成时间戳，毫秒级
    time_stamp = int(round(time.time() * 1000))
    url = 'https://www.jin10.com/flash_newest.js?t=%d' % time_stamp
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:67.0) Gecko/20100101 Firefox/67.0", }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    html = response.text
    # print(html)

    # 提取json
    sql = "REPLACE INTO `news` VALUES "
    json_str = html.replace('var newest = ', '')[0:-1]
    json_obj = json.loads(json_str)
    # 提取新闻内容，存入数据库
    for i in range(0, len(json_obj)):
        try:
            news_time = json_obj[i]['time']
            if news_time > last_time:
                news_time = datetime.strptime(news_time, "%Y-%m-%d %H:%M:%S")
                news_remarks = json_obj[i]['id']
                news_url = 'https://www.jin10.com/detail/%s' % news_remarks
                try:
                    content = json_obj[i]['data']['content'].replace("'", '"')
                    if len(content) > 0:
                        sql += "('%s', '%s', '金十数据', '%s', '%s')," % (news_time, content, news_url, news_remarks)
                except Exception as e:
                    pass
        except Exception as e:
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(round(time.time())))
            dingtalk.send_text(now + '新闻采集发生错误\n金十数据：' + str(e))
    set_db(sql)


def get_jin10fut(last_time):
    url = 'https://qh-flash-api.jin10.com/get_flash_list?channel=-1'
    headers1 = {'accept': '*/*',
                'accept-encoding': 'gzip, deflate, br',
                'accept-language': 'zh-CN,zh;q=0.9',
                'access-control-request-headers': 'x-app-id,x-version',
                'access-control-request-method': 'GET',
                'cache-control': 'no-cache',
                'origin': 'https://qihuo.jin10.com',
                'pragma': 'no-cache',
                'referer': 'https://qihuo.jin10.com/',
                'user-agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) '
                              'Chrome/79.0.3945.79 Safari/537.36 '
                }
    response0 = requests.options(url, headers=headers1)
    # print(response0.status_code)  # 发送OPTIONS，返回204

    headers2 = {'accept': 'application/json, text/plain, */*',
                'accept-encoding': 'gzip, deflate',
                'accept-language': 'zh-CN,zh;q=0.9',
                'cookie': 'UM_distinctid=18594f2b3d4bac-0a81af6fa325b-5040231b-295d29-18594f2b3d5c26; x-token=; Hm_lvt_522b01156bb16b471a7e2e6422d272ba=1673247672',
                'origin': 'https://qihuo.jin10.com',
                'referer': 'https://qihuo.jin10.com/',
                'sec-fetch-mode': 'cors',
                'sec-fetch-site': 'same-site',
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/79.0.3945.79 Safari/537.36',
                'x-app-id': 'KxBcVoDHStE6CUkQ',
                'x-version': '1.0.0',
                }
    response = requests.get(url, headers=headers2)
    # response.encoding = 'utf-8'
    # print(response.encoding)

    # 提取新闻内容，存入数据库
    json_obj = json.loads(response.text)
    json_obj = json_obj['data']
    # print(json_obj)
    sql = "REPLACE INTO `news` VALUES "
    for i in range(0, len(json_obj)):
        try:
            local_time = json_obj[i]['time']
            if local_time > last_time:
                news_remarks = json_obj[i]['id']
                news_url = 'https://flash.jin10.com/detail/%s' % news_remarks
                try:
                    content = json_obj[i]['data']['content'].replace("'", '"')
                    if len(content) > 0:
                        sql += "('%s', '%s', '金十期货', '%s', '%s')," % (local_time, content, news_url, news_remarks)
                except Exception as e:
                    pass
        except Exception as e:
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(round(time.time())))
            dingtalk.send_text(now + '新闻采集发生错误\n金十期货：' + str(e))
    set_db(sql)


def get_sina7x24(last_time):
    url = 'http://zhibo.sina.com.cn/api/zhibo/feed?callback=jQuery11120018441662990165142_' + \
          str(round(time.time() * 1000)) + '&page=1&page_size=20&zhibo_id=152&tag_id=0&dire=f&dpc=1&pagesize=20'
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:67.0) Gecko/20100101 Firefox/67.0", }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    html = response.text

    # 提取json
    pos1 = html.find('{"result"')
    pos2 = html.find(');}catch(e){};')
    json_str = html[pos1:pos2]
    json_obj = json.loads(json_str)['result']['data']['feed']['list']

    sql = "REPLACE INTO `news` VALUES "
    for d in json_obj:
        try:
            local_time = d['create_time']
            if local_time > last_time:
                news_remarks = str(d['id'])
                news_url = 'https://finance.sina.com.cn/7x24/notification.shtml?id=%s' % news_remarks
                try:
                    content = d['rich_text'].replace("'", '"')
                    if len(content) > 0:
                        sql += "('%s', '%s', '新浪财经', '%s', '%s')," % (local_time, content, news_url, news_remarks)
                except Exception as e:
                    pass
        except Exception as e:
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(round(time.time())))
            dingtalk.send_text(now + '新闻采集发生错误\n新浪财经：' + str(e))
    set_db(sql)


def get_cls(last_time):
    last_time = int(last_time)
    url = ('https://www.cls.cn/nodeapi/updateTelegraphList?app=CailianpressWeb&category=&hasFirstVipArticle=1&'
           'lastTime=%d&os=web&rn=20&subscribedColumnIds=') % last_time
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:67.0) Gecko/20100101 Firefox/67.0", }
    response = requests.get(url, headers=headers)
    response.encoding = 'utf-8'
    # print(response.text)

    sql = "REPLACE INTO `news` VALUES "
    json_obj = json.loads(response.text)
    for d in json_obj['data']['roll_data']:
        try:
            if d['ctime'] > last_time:
                local_time = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(d['ctime']))
                content = d['content'].replace("'", '"')
                news_remarks = d['id']
                news_url = d['shareurl']
                sql += "('%s', '%s', '财联社', '%s', '%s')," % (local_time, content, news_url, news_remarks)
        except Exception as e:
            now = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(round(time.time())))
            dingtalk.send_text(now + '新闻采集发生错误\n财联社：' + str(e))
    set_db(sql)


def check_db():
    # 获取上次新闻时间，并检测新闻源是否正常
    d = {
        '金十数据': [0, datetime(2024, 5, 1, 0, 0, 0)],
        '金十期货': [0, datetime(2024, 5, 1, 0, 0, 0)],
        '新浪财经': [0, datetime(2024, 5, 1, 0, 0, 0)],
        '财联社': [0, datetime(2024, 5, 1, 0, 0, 0)],
    }
    sql = ("SELECT source, COUNT(source) AS count, MAX(news_time) AS latest_time from news WHERE news_time >= "
           "(NOW() - INTERVAL 3 HOUR) GROUP BY source;")
    r = get_data(sql)
    for row in r:
        d[row[0]][0] = row[1]
        d[row[0]][1] = row[2]

    for k, v in d.items():
        if 0 == v[0]:
            dingtalk.send_text('新闻采集系统：【%s】疑似失效，请尽快检查！' % k, at_all=True)
        print(k, v)
    return d


if __name__ == '__main__':
    info = check_db()
    get_jin10(info['金十数据'][1].strftime("%Y-%m-%d %H:%M:%S"))
    get_jin10fut(info['金十期货'][1].strftime("%Y-%m-%d %H:%M:%S"))
    get_sina7x24(info['新浪财经'][1].strftime("%Y-%m-%d %H:%M:%S"))
    get_cls(info['财联社'][1].timestamp())
