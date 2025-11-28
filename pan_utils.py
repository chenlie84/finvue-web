import time
import requests
import random

access_key = 'A9GB4FCO9BJZOWY60OOV'
secret_key = 'x3ecBEjD7ZABGf5yW51CegFh442f865LqLVFxeAZ'
bucket = 'yxd-risk-public-read'
name = 'yxd-risk'
sharer = 'xuzhao29'
valid_time = 60 * 24 * 365 * 1  # 1年
url_base = 'http://pan.paas.paas.corp/share/gen'



def md5_str(s):
    import hashlib
    m = hashlib.md5()
    m.update(s.encode('utf-8'))
    return m.hexdigest()


def get_sign(s_data, timestamp, nonce):
    param_list = list()
    for k, v in s_data.items():
        param_list.append(k + '=' + str(v))

    sign_str = ':'.join([access_key, '&'.join(sorted(param_list)), str(timestamp), nonce, secret_key])
    return md5_str(sign_str)


def get_share_url(query, body):
    headers = {
        'Content-Type': 'application/json'
    }
    response = requests.post(url_base, params=query, json=body, headers=headers)
    return response.json()


def generate_nonce():
    return ''.join([str(random.randint(0, 9)) for _ in range(4)])


def make_share_url(target_paths):
    for target_path in target_paths:
        timestamp = int(time.time())
        nonce = generate_nonce()  # 随机字符串

        sign_data = {
            'bucket': bucket,
            'name': name,
            'public': 'true',
            'sharer': sharer,
            'targetPath': target_path,
            'validTime': valid_time
        }

        sign = get_sign(sign_data, timestamp, nonce)

        query_params = {
            'accessKey': access_key,
            'timestamp': timestamp,
            'nonce': nonce,
            'sign': sign
        }

        body_params = {
            'bucket': bucket,
            'targetPath': target_path,
            'validTime': valid_time,
            'sharer': sharer,
            'name': name,
            'public': True
        }

        resp = get_share_url(query_params, body_params)
        print(resp)



if __name__ == '__main__':
    target_paths = [
        'data_viz/crs.png',
    ]
    make_share_url(target_paths)

