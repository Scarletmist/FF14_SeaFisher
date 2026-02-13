from datetime import datetime, timedelta
import math
from zoneinfo import ZoneInfo

BAIT_CHT = {
    'Glowworm': '火螢',
    'Shrimp Cage': '小蝦肉籠',
    'Heavy Steel Jig': '重鐵板鉤',
    'Rat Tail': '溝鼠尾巴',
    'Squid Strip': '烏賊絲',
    'Pill Bug': '潮蟲',
    'Ragworm': '石沙蠶',
    'Krill': '磷蝦',
    'Plump Worm': '海腸',
    'Mackerel Strip': '青花魚塊',
    'Stonefly Nymph': '石蠅幼蟲'
}

BAIT_SOURCE = {
    'Glowworm': '海都市場─工具商',
    'Shrimp Cage': '海都市場─工具商',
    'Heavy Steel Jig': '金工40級製作',
    'Rat Tail': '海都市場─工具商',
    'Squid Strip': '海釣碼頭─工票交易員(需解5.0藍++)',
    'Pill Bug': '海都市場─工具商',
    'Mackerel Strip': '海釣碼頭─工票交易員(需解6.0藍++)',
    'Stonefly Nymph': '3.0以上都市─工具商'
}

COLOR_CHT = {
    'Red': '紅',
    'Green': '綠'
}

NEAR_PATTERN = [
    'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN',
    'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD',
    'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD',
    'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND',
    'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD',
    'TS', 'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS',
    'NS', 'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS',
    'RS', 'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS',
    'BN', 'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS',
    'TN', 'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN',
    'NN', 'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN',
    'RN', 'BD', 'TD', 'ND', 'RD', 'BS', 'TS', 'NS', 'RS', 'BN', 'TN', 'NN'
]

FAR_PATTERN = [
    'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN',
    'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD',
    'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD',
    'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS',
    'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS',
    'SN', 'AD', 'SD', 'AS', 'SS', 'AN', 'SN', 'AD', 'SD', 'AS', 'SS', 'AN'
]

AREA = ['OGB', 'SSM', 'NSM', 'ORS', 'CM', 'OBS', 'OTS', 'OSS', 'KC', 'OR', 'LOR']

TIME_LIST = ['D', 'S', 'N']

SPEC_BAIT = {
    'OGB': 'Plump Worm',
    'SSM': 'Krill',
    'NSM': 'Ragworm',
    'ORS': 'Plump Worm',
    'CM': 'Ragworm',
    'OBS': 'Krill',
    'OTS': 'Plump Worm',
    'OSS': 'Plump Worm',
    'KC': 'Ragworm',
    'OR': 'Krill',
    'LOR': 'Plump Worm'
}  # 普通海域幻光魚餌

SPEC_COLOR = {
    'OGB': 'Red',
    'SSM': 'Green',
    'NSM': 'Green',
    'ORS': 'Red',
    'CM': 'Green',
    'OBS': 'Red',
    'OTS': 'Red',
    'OSS': 'Red',
    'KC': 'Red',
    'OR': 'Red',
    'LOR': 'Red'
}  # 普通海域幻光拉餌顏色

AREA_MAPPING = {
    'B': ['CM', 'NSM', 'OBS'],
    'T': ['CM', 'ORS', 'OTS'],
    'N': ['SSM', 'OGB', 'NSM'],
    'R': ['OGB', 'SSM', 'ORS'],
    'S': ['OSS', 'KC', 'OR'],
    'A': ['OSS', 'KC', 'LOR']
}

OROLA_BAIT = {
    'OGB': {
        'D': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Glowworm', 'KING': True, 'MOOCH': False, 'COLOR': 'Red'}
    },
    'SSM': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': True},
        'N': {'BAIT': 'Shrimp Cage', 'KING': True, 'MOOCH': True, 'COLOR': 'Red'}
    },
    'NSM': {
        'D': {'BAIT': 'Heavy Steel Jig', 'KING': True, 'MOOCH': False, 'COLOR': 'Red'},
        'S': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False}
    },
    'ORS': {
        'D': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Rat Tail', 'KING': True, 'MOOCH': False, 'COLOR': 'Red'},
        'N': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False}
    },
    'CM': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Squid Strip', 'KING': True, 'MOOCH': False, 'COLOR': 'Red'}
    },
    'OBS': {
        'D': {'BAIT': 'Ragworm', 'KING': True, 'MOOCH': False, 'KING_BAIT': 'Pill Bug', 'COLOR': 'Green'},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False}
    },
    'OTS': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': True},
        'S': {'BAIT': 'Krill', 'KING': True, 'MOOCH': True, 'COLOR': 'Red'},
        'N': {'BAIT': 'Krill', 'KING': False, 'MOOCH': True}
    },
    'OSS': {
        'D': {'BAIT': 'Krill', 'KING': True, 'MOOCH': False, 'KING_BAIT': 'Mackerel Strip', 'COLOR': 'Green'},
        'S': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
    }, 
    'KC': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Plump Worm', 'KING': True, 'MOOCH': True, 'COLOR': 'Red'},
    }, 
    'OR': {
        'D': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Plump Worm', 'KING': True, 'MOOCH': False, 'KING_BAIT': 'Squid Strip', 'COLOR': 'Red'},
        'N': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
    }, 
    'LOR': {
        'D': {'BAIT': 'Stonefly Nymph', 'KING': True, 'MOOCH': False, 'COLOR': 'Red'},
        'S': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
    }
}   # 幻海注意事項

TWO_HOURS = 2 * 60 * 60
OFFSET = 132


def next_even_hour_full(now=None, threshold_minute=30, include_equal=True):
    """
    取得目標整點（偶數小時）。
    參數:
      now: datetime 或 None（None 時使用系統當前時間）
      threshold_minute: 判斷門檻（預設30）
      include_equal: 是否把等於 threshold_minute 視為 "已到門檻"（預設 True）
    回傳: datetime（目標整點）
    """
    if now is None:
        now = datetime.now()
    minute = now.minute
    cmp = (minute >= threshold_minute) if include_equal else (minute > threshold_minute)
    if now.hour % 2 == 0:  # 偶數小時
        delta_hours = 2 if cmp else 0
    else:  # 奇數小時
        delta_hours = 1
    base = now.replace(minute=0, second=0, microsecond=0)
    return base + timedelta(hours=delta_hours)


def get_route(targetDate: datetime):
    first_date = datetime(1970, 1, 1, tzinfo=ZoneInfo("Asia/Taipei"))
    voyageNumber = math.floor((targetDate - first_date).total_seconds() / TWO_HOURS)
    nesr_index = (OFFSET + voyageNumber) % len(NEAR_PATTERN)
    far_index = (OFFSET + voyageNumber) % len(FAR_PATTERN)

    near_route = NEAR_PATTERN[nesr_index]
    far_route = FAR_PATTERN[far_index]

    return near_route, far_route


def get_bait(rawDate: datetime=datetime.now(tz=ZoneInfo("Asia/Taipei"))):
    targetDate = next_even_hour_full(rawDate)
    near_route_time, far_route_time = get_route(targetDate)

    messages = []
    messages.append(f'航線時間: {targetDate.strftime("%Y/%m/%d %H:%M")}')

    for fish_route_time in (near_route_time, far_route_time):
        messages.append('=' * 28)
        if fish_route_time == near_route_time:
            messages.append('> **（近海航線）**')
        else:
            messages.append('> **（遠洋航線）**')
        route = fish_route_time[0]
        time = fish_route_time[1]
        time_index = TIME_LIST.index(time)

        for i in range(3):
            messages.append('> ' + '=' * 20)
            area = AREA_MAPPING[route][i]
            spec_bait = SPEC_BAIT[area]
            orola = OROLA_BAIT[area][TIME_LIST[(time_index + i) % 3]]

            messages.append(f'> 釣場 No.{i + 1}, 釣餌: [ {BAIT_CHT[spec_bait]} ], !!!{COLOR_CHT[SPEC_COLOR[area]]}色')
            messages.append(f'> 幻海釣餌: [ {BAIT_CHT[orola['BAIT']]} ]' + (', 以小釣大' if orola['MOOCH'] else ''))
            if orola['KING']:
                messages.append(f'>     !!!幻海海王!!!' + (f', 釣餌: [ {BAIT_CHT[orola["KING_BAIT"]]} ]' if "KING_BAIT" in orola else '') + f', !!!{COLOR_CHT[orola["COLOR"]]}色')
                if orola['BAIT'] in BAIT_SOURCE:
                    messages.append(f'>        魚餌取得方式: {BAIT_SOURCE[orola["BAIT"]]}')
                if "KING_BAIT" in orola and orola['KING_BAIT'] in BAIT_SOURCE:
                    messages.append(f'>        魚餌取得方式: {BAIT_SOURCE[orola["KING_BAIT"]]}')

    messages.append('=' * 28)
    
    return "\n".join(messages)


def get_source():
    messages = ["幻海海王魚餌取得方式:"]
    for name, source in BAIT_SOURCE.items():
        cht_name = BAIT_CHT[name]
        messages.append(cht_name + '　' * (4 - len(cht_name)) + f': {source}')
    return "\n".join(messages)


current_time = datetime.now(tz=ZoneInfo("Asia/Taipei"))
print(get_bait(current_time + timedelta(hours=6)))
