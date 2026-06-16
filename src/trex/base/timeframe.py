from __future__ import annotations
"""trex.base.timeframe — Timeframe string constants."""


class Timeframe(str):
    """String subclass با named constants برای هر timeframe پشتیبانی‌شده."""

    m1 = "1m";   m2 = "2m";   m3 = "3m";   m4 = "4m";   m5 = "5m"
    m6 = "6m";   m7 = "7m";   m8 = "8m";   m9 = "9m";   m10 = "10m"
    m11 = "11m"; m12 = "12m"; m13 = "13m"; m14 = "14m"; m15 = "15m"
    m16 = "16m"; m17 = "17m"; m18 = "18m"; m19 = "19m"; m20 = "20m"
    m21 = "21m"; m22 = "22m"; m23 = "23m"; m24 = "24m"; m25 = "25m"
    m26 = "26m"; m27 = "27m"; m28 = "28m"; m29 = "29m"; m30 = "30m"
    m31 = "31m"; m32 = "32m"; m33 = "33m"; m34 = "34m"; m35 = "35m"
    m36 = "36m"; m37 = "37m"; m38 = "38m"; m39 = "39m"; m40 = "40m"
    m41 = "41m"; m42 = "42m"; m43 = "43m"; m44 = "44m"; m45 = "45m"
    m46 = "46m"; m47 = "47m"; m48 = "48m"; m49 = "49m"; m50 = "50m"
    m51 = "51m"; m52 = "52m"; m53 = "53m"; m54 = "54m"; m55 = "55m"
    m56 = "56m"; m57 = "57m"; m58 = "58m"; m59 = "59m"

    h1  = "1H";  h2  = "2H";  h3  = "3H";  h4  = "4H";  h5  = "5H"
    h6  = "6H";  h7  = "7H";  h8  = "8H";  h9  = "9H";  h10 = "10H"
    h11 = "11H"; h12 = "12H"; h13 = "13H"; h14 = "14H"; h15 = "15H"
    h16 = "16H"; h17 = "17H"; h18 = "18H"; h19 = "19H"; h20 = "20H"
    h21 = "21H"; h22 = "22H"; h23 = "23H"

    D1 = "1D"; D2 = "2D"; D3 = "3D"
    W1 = "1W"


__all__ = ["Timeframe"]
