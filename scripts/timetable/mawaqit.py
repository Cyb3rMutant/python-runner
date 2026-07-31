from calendar import monthrange
from datetime import datetime, timezone
from io import StringIO
from zoneinfo import ZoneInfo

import pandas as pd
import requests

YEAR = 2026

URL = "https://downloads.salahtimes.com/api/prayerDownload"

HEADERS = {
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
}

UK = ZoneInfo("Europe/London")


def download_csv(start_date, end_date, hanafi=False):
    if hanafi:
        hlm = "3"
        acm = "2"
    else:
        hlm = "4"
        acm = "1"

    params = {
        "format": "csv",
        "country": "uk",
        "place": "bristol",
        "hlm": hlm,
        "pcm": "5",
        "acm": acm,
        "ds": start_date.strftime("%Y-%m-%d"),
        "de": end_date.strftime("%Y-%m-%d"),
        "as24": "true",
    }

    response = requests.get(URL, headers=HEADERS, params=params)
    response.raise_for_status()

    return pd.read_csv(StringIO(response.text))


def to_gmt(date_string, time_string):
    """
    Convert a UK local prayer time to GMT (winter time).
    """

    # Example:
    # date_string = "Wed 1 Jul 2026"
    # time_string = "21:30"

    local = datetime.strptime(
        f"{date_string} {time_string}",
        "%a %d %b %Y %H:%M",
    ).replace(tzinfo=UK)

    gmt = local.astimezone(timezone.utc)

    return gmt.strftime("%H:%M")


def build_month(month):
    start = datetime(YEAR, month, 1)
    end = datetime(YEAR, month, monthrange(YEAR, month)[1])

    shafi = download_csv(start, end, hanafi=False)
    hanafi = download_csv(start, end, hanafi=True)

    output = pd.DataFrame()

    output["Day"] = shafi["Date"].str.extract(r"(\d{1,2})")[0].str.zfill(2)

    output["Fajr"] = shafi["Fajr"]
    output["Shuruk"] = shafi["Sunrise"]
    output["Duhr"] = shafi["Dhuhr"]
    output["Asr"] = shafi["Asar"]  # Hanafi Asr
    output["Maghrib"] = shafi["Maghrib"]
    output["Isha"] = hanafi["Isha"]  # Change to hanafi["Isha"] if desired

    prayer_columns = [
        "Fajr",
        "Shuruk",
        "Duhr",
        "Asr",
        "Maghrib",
        "Isha",
    ]

    for column in prayer_columns:
        output[column] = [
            to_gmt(date, time) for date, time in zip(shafi["Date"], output[column])
        ]

    filename = f"{YEAR}-{month:02d}.csv"
    output.to_csv(filename, index=False)

    print(f"✓ Created {filename}")


def main():
    for month in range(1, 13):
        build_month(month)

    print("\nDone!")


if __name__ == "__main__":
    main()
