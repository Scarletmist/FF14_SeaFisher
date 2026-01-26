from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import math
import re
from typing import Tuple

# Eorzea 時間常數（以秒為單位）
YEAR = 33177600
MONTH = 2764800
DAY = 86400
HOUR = 3600
MINUTE = 60
SECOND = 1

# 轉換常數：地球秒 * EORZEA_TIME_CONSTANT = Eorzea 秒
EORZEA_TIME_CONSTANT: float = 3600.0 / 175.0  # = 20.571428...

@dataclass
class EorzeaTime:
    """Eorzea 時間資料結構（全部為整數）"""
    year: int
    month: int
    day: int
    hour: int
    minute: int
    second: int

    def __str__(self) -> str:
        return f"{self.year}-{self.month:02d}-{self.day:02d} {self.hour:02d}:{self.minute:02d}:{self.second:02d}"

    def get_date(self) -> str:
        return f"{self.year}{self.month:02d}{self.day:02d}"

def _zero_pad(value: int) -> str:
    """回傳二位數字字串（不足補 0）"""
    return f"{value:02d}"

def convert_to_eorzea_time(t: datetime) -> EorzeaTime:
    """
    將 Earth (UTC) datetime 轉為 EorzeaTime
    輸入 t 建議為 UTC 時區的 datetime（若不是則會以 timestamp 處理）
    """
    # 以 UTC epoch 秒數為基準
    earth_seconds = t.astimezone(tz=timezone.utc).replace(tzinfo=timezone.utc).timestamp()
    eorzea_seconds = int(math.floor(earth_seconds * EORZEA_TIME_CONSTANT))

    year = eorzea_seconds // YEAR + 1
    month = (eorzea_seconds // MONTH) % 12 + 1
    day = (eorzea_seconds // DAY) % 32 + 1
    hour = (eorzea_seconds // HOUR) % 24
    minute = (eorzea_seconds // MINUTE) % 60
    second = eorzea_seconds % 60

    return EorzeaTime(year=year, month=month, day=day, hour=hour, minute=minute, second=second)


def get_ore(t: datetime, ores, noticed, reset_date) -> str:
    five_min_eoz_time = convert_to_eorzea_time(datetime.now() + timedelta(minutes=5))
    if five_min_eoz_time.hour == 0 and five_min_eoz_time.get_date() != reset_date:
        RESET_DATE = five_min_eoz_time.get_date()
        noticed = []

    if five_min_eoz_time.hour not in noticed:
        noticed.append(five_min_eoz_time.hour)
        messages = []

        for ore, ore_info in ores.items():
            if int(ore_info['time']) == five_min_eoz_time.hour:
                messages.append(f'{ore} ( {ore_info["place"]} )')
        
        if len(messages) > 0:
            messages.insert(0, '限時礦物:')
            return '\n'.join(messages)
        else:
            return ''
    else:
        return ''


TEST_ORE = {
    'TEST': {
        'time': 6,
        'place': 'test'
    }
}
print(get_ore(datetime.now(), TEST_ORE, [], ''))
