from pylatex.utils import bold


class ClassRow:
    def __init__(self, text, bold=False):
        self.text = text
        self.bold = bold


def add_class(t, c, b=False):
    if b:
        c = bold(c)
    t.add_hline()
    t.add_row([c])


def add_classes(t, classes):
    for c in classes:
        add_class(t, c.text, c.bold)
    t.add_hline()
    return t


import math
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo


class PrayTime:
    def __init__(
        self,
        location=[51.4545, -2.5879],
        tz="Europe/London",
        fajr_angle=15,
        isha_angle=15,
    ):
        self.location = location
        self.tz = ZoneInfo(tz)
        self.fajr_angle = fajr_angle
        self.isha_angle = isha_angle

    def times(self, d):
        self.utc_date = datetime(d.year, d.month, d.day, tzinfo=timezone.utc)
        times = self._compute_times()
        return {key: self._format_time(value) for key, value in times.items()}

    # ---------------------- Compute Times -----------------------

    def _compute_times(self):
        horizon = 0.833

        sunrise = self._angle_time(horizon, 6, -1)
        sunset = self._angle_time(horizon, 18)
        night = 24 + sunrise - sunset

        # Fajr: angle-based, capped so it never creeps more than fajr_angle/60
        # of the night before sunrise (matters near midsummer at this latitude)
        fajr = self._angle_time(self.fajr_angle, 5, -1)
        fajr_portion = (self.fajr_angle / 60) * night
        if math.isnan(fajr) or sunrise - fajr > fajr_portion:
            fajr = sunrise - fajr_portion

        dhuhr = self._mid_day(12)
        asr = self._angle_time(self._asr_angle(1, 13), 13)
        asr_hanafi = self._angle_time(self._asr_angle(2, 13), 13)
        maghrib = sunset + 1 / 60

        # Isha: angle-based, capped by the one-seventh-of-the-night rule
        isha = self._angle_time(self.isha_angle, 18)
        isha_portion = night / 7
        if math.isnan(isha) or isha - sunset > isha_portion:
            isha = sunset + isha_portion

        return self._convert_times(
            {
                "fajr": fajr,
                "sunrise": sunrise,
                "dhuhr": dhuhr,
                "asr shafi": asr,
                "asr hanafi": asr_hanafi,
                "maghrib": maghrib,
                "isha": isha,
            }
        )

    # convert local solar times to UTC datetimes
    def _convert_times(self, times):
        lng = self.location[1]
        out = {}
        for key, value in times.items():
            if math.isnan(value):
                out[key] = None
                continue
            t = value - lng / 15
            out[key] = self._round_time(self.utc_date + timedelta(hours=t))
        return out

    def _round_time(self, dt):
        epoch = dt.timestamp()
        return datetime.fromtimestamp(round(epoch / 60) * 60, tz=timezone.utc)

    # ---------------------- Calculation Functions -----------------------

    def _sun_position(self, time):
        lng = self.location[1]
        utc_days = (
            self.utc_date - datetime(1970, 1, 1, tzinfo=timezone.utc)
        ).total_seconds() / 86400
        D = utc_days - 10957.5 + time / 24 - lng / 360

        g = self._mod(357.529 + 0.98560028 * D, 360)
        q = self._mod(280.459 + 0.98564736 * D, 360)
        L = self._mod(q + 1.915 * self._sin(g) + 0.02 * self._sin(2 * g), 360)
        e = 23.439 - 0.00000036 * D
        RA = self._mod(
            self._arctan2(self._cos(e) * self._sin(L), self._cos(L)) / 15, 24
        )

        return {
            "declination": self._arcsin(self._sin(e) * self._sin(L)),
            "equation": q / 15 - RA,
        }

    def _mid_day(self, time):
        eqt = self._sun_position(time)["equation"]
        return self._mod(12 - eqt, 24)

    # compute the time when the sun reaches a specific angle below the horizon
    def _angle_time(self, angle, time, direction=1):
        lat = self.location[0]
        decl = self._sun_position(time)["declination"]
        numerator = -self._sin(angle) - self._sin(lat) * self._sin(decl)
        diff = self._arccos(numerator / (self._cos(lat) * self._cos(decl))) / 15
        return self._mid_day(time) + diff * direction

    # shadow_factor: 1 = Standard/Shafi, 2 = Hanafi
    def _asr_angle(self, shadow_factor, time):
        lat = self.location[0]
        decl = self._sun_position(time)["declination"]
        return -self._arccot(shadow_factor + self._tan(abs(lat - decl)))

    # ---------------------- Formatting -----------------------

    def _format_time(self, dt):
        if dt is None:
            return "-----"
        return dt.astimezone(self.tz).strftime("%H:%M")

    # ---------------------- Misc -----------------------

    @staticmethod
    def _mod(a, b):
        return (a % b + b) % b

    # --------------------- Degree-Based Trigonometry -----------------

    @staticmethod
    def _dtr(d):
        return d * math.pi / 180

    @staticmethod
    def _rtd(r):
        return r * 180 / math.pi

    def _sin(self, d):
        return math.sin(self._dtr(d))

    def _cos(self, d):
        return math.cos(self._dtr(d))

    def _tan(self, d):
        return math.tan(self._dtr(d))

    def _arcsin(self, x):
        if abs(x) > 1:
            return float("nan")
        return self._rtd(math.asin(x))

    def _arccos(self, x):
        if abs(x) > 1:
            return float("nan")
        return self._rtd(math.acos(x))

    def _arccot(self, x):
        return self._rtd(math.atan(1 / x))

    def _arctan2(self, y, x):
        return self._rtd(math.atan2(y, x))


def get_prayer_times(
    d, location=[51.4545, -2.5879], tz="Europe/London", fajr_angle=15, isha_angle=15
):
    return PrayTime(location, tz, fajr_angle, isha_angle).times(d)


def add_ramadan_columns(dt):
    dt.insert(loc=0, column="Hijri", value=[x for x in range(1, 31)])
    dt.insert(
        loc=10,
        column="Taraweeh",
        value=["19:20"] * 10 + ["19:40"] * 10 + ["20:00"] * 9 + ["N/A"],
    )
    return dt
