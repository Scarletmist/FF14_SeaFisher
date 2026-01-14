from datetime import datetime, timedelta
import math

BAIT_CHT = {
    'Glowworm': '火螢',
    'Shrimp Cage': '小蝦肉籠',
    'Heavy Steel Jig': '重鐵板鉤',
    'Rat Tail': '溝鼠尾巴',
    'Squid Strip': '烏賊絲',
    'Pill Bug': '潮蟲',
    'Ragworm': '石沙蠶',
    'Krill': '磷蝦',
    'Plump Worm': '海腸'
}

COLOR_CHT = {
    'Red': '紅',
    'Green': '綠'
}

PATTERN = [
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

AREA = ['OGB', 'SSM', 'NSM', 'ORS', 'CM', 'OBS', 'OTS']

TIME_LIST = ['D', 'S', 'N']

SPEC_BAIT = {
    'OGB': 'Plump Worm',
    'SSM': 'Krill',
    'NSM': 'Ragworm',
    'ORS': 'Plump Worm',
    'CM': 'Ragworm',
    'OBS': 'Krill',
    'OTS': 'Plump Worm'
}

SPEC_COLOR = {
    'OGB': 'Red',
    'SSM': 'Green',
    'NSM': 'Green',
    'ORS': 'Red',
    'CM': 'Green',
    'OBS': 'Red',
    'OTS': 'Red'
}

AREA_MAPPING = {
    'B': ['CM', 'NSM', 'OBS'],
    'T': ['CM', 'ORS', 'OTS'],
    'N': ['SSM', 'OGB', 'NSM'],
    'R': ['OGB', 'SSM', 'ORS']
}

OROLA_BAIT = {
    'OGB': {
        'D': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Glowworm', 'KING': True, 'MOOCH': False}
    },
    'SSM': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': True},
        'N': {'BAIT': 'Shrimp Cage', 'KING': True, 'MOOCH': True}
    },
    'NSM': {
        'D': {'BAIT': 'Heavy Steel Jig', 'KING': True, 'MOOCH': False},
        'S': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False}
    },
    'ORS': {
        'D': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Rat Tail', 'KING': True, 'MOOCH': False},
        'N': {'BAIT': 'Ragworm', 'KING': False, 'MOOCH': False}
    },
    'CM': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': False},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Squid Strip', 'KING': True, 'MOOCH': False}
    },
    'OBS': {
        'D': {'BAIT': 'Ragworm', 'KING': True, 'MOOCH': False, 'KING_BAIT': 'Pill Bug'},
        'S': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False},
        'N': {'BAIT': 'Plump Worm', 'KING': False, 'MOOCH': False}
    },
    'OTS': {
        'D': {'BAIT': 'Krill', 'KING': False, 'MOOCH': True},
        'S': {'BAIT': 'Krill', 'KING': True, 'MOOCH': True},
        'N': {'BAIT': 'Krill', 'KING': False, 'MOOCH': True}
    }
}

TWO_HOURS = 2 * 60 * 60
OFFSET = 88

def get_route(targetDate: datetime):
    first_date = datetime(1970, 1, 1)
    voyageNumber = math.floor((targetDate - first_date).total_seconds() / TWO_HOURS)
    index = (OFFSET + voyageNumber) % len(PATTERN)

    route = PATTERN[index]

    return route


def get_bait(targetDate: datetime):
    fish_route_time = get_route(targetDate)
    route = fish_route_time[0]
    time = fish_route_time[1]
    time_index = TIME_LIST.index(time)

    messages = []

    for i in range(3):
        area = AREA_MAPPING[route][i]
        spec_bait = SPEC_BAIT[area]
        orola = OROLA_BAIT[area][TIME_LIST[(time_index + i) % 3]]

        messages.append(f'釣場 No.{i + 1}, 釣餌: [ {BAIT_CHT[spec_bait]} ], !!!{COLOR_CHT[SPEC_COLOR[area]]}色')
        messages.append(f'幻海釣餌: [ {BAIT_CHT[orola['BAIT']]} ]' + (', 以小釣大' if orola['MOOCH'] else ''))
        if orola['KING']:
            messages.append(f'    !!!幻海海王!!!' + (f', 釣餌: [ {BAIT_CHT[orola["KING_BAIT"]]} ]' if "KING_BAIT" in orola else ''))
        messages.append('=' * 20)
    
    return "\n".join(messages)
