"""
trex.indicators — SeriesDefinition presets.

This module only builds display contracts (SeriesDef objects) that tell
the terminal how to render a series.  It contains zero math.

You compute values with whatever library you prefer — pandas-ta, ta-lib,
vectorbt, numpy, or your own code — then push them via
``session.push_indicators({"rsi14": points})``.

Usage::

    from trex.indicators import Overlay, Oscillator, Volume

    definitions = [
        Overlay.sma(20),
        Overlay.ema(50, color="#FF9800"),
        *Overlay.bollinger(20),
        Oscillator.rsi(14),
        *Oscillator.macd(),
        Volume.bars(),
    ]
    await session.define(*definitions)

    # Later, push your computed values:
    import pandas_ta as ta
    rsi = ta.rsi(closes, length=14)
    await session.push_indicators({
        "rsi14": [Point(t, v) for t, v in zip(times, rsi.dropna())]
    })
"""
from __future__ import annotations
from typing import Optional
from trex.domain.types import SeriesDef, Level


# ── internal helpers ──────────────────────────────────────────────────

def _overlay(key: str, label: str, color: str, *,
             width: int = 1, style: int = 0,
             pane_id: Optional[str] = None, **kw) -> SeriesDef:
    return SeriesDef(key=key, label=label, pane="main", kind="line",
                     color=color, width=width, style=style,
                     pane_id=pane_id or key, **kw)


def _sub(key: str, label: str, color: str, pane_id: str, *,
         height: int = 120, width: int = 1, style: int = 0,
         levels: Optional[list[Level]] = None, **kw) -> SeriesDef:
    return SeriesDef(key=key, label=label, pane="sub", kind="line",
                     color=color, width=width, style=style,
                     pane_id=pane_id, pane_height=height,
                     levels=levels or [], **kw)


def _hist(key: str, label: str, pane_id: str, *,
          up: str = "#089981", dn: str = "#F23645",
          height: int = 120, **kw) -> SeriesDef:
    return SeriesDef(key=key, label=label, pane="sub", kind="histogram",
                     color=up, color_pos=up, color_neg=dn,
                     pane_id=pane_id, pane_height=height, **kw)


def _rsi_levels() -> list[Level]:
    return [Level(70, "#EF5350", 2, "OB"),
            Level(50, "#454560", 2, ""),
            Level(30, "#26A69A", 2, "OS")]


def _stoch_levels() -> list[Level]:
    return [Level(80, "#EF5350", 2, ""),
            Level(20, "#26A69A", 2, "")]


# ══════════════════════════════════════════════════════════════════════
# Overlay indicators  (rendered on the main price pane)
# ══════════════════════════════════════════════════════════════════════

class Overlay:
    """SeriesDef factories for main-pane overlays."""

    # ── Moving averages ──────────────────────────────────────────────

    @staticmethod
    def sma(period: int = 20, *, color: str = "#26A69A",
            key: Optional[str] = None) -> SeriesDef:
        """Simple Moving Average."""
        k = key or f"sma{period}"
        return _overlay(k, f"SMA {period}", color)

    @staticmethod
    def ema(period: int = 20, *, color: str = "#FF9800",
            key: Optional[str] = None) -> SeriesDef:
        """Exponential Moving Average."""
        k = key or f"ema{period}"
        return _overlay(k, f"EMA {period}", color)

    @staticmethod
    def wma(period: int = 20, *, color: str = "#E91E63",
            key: Optional[str] = None) -> SeriesDef:
        """Weighted Moving Average."""
        k = key or f"wma{period}"
        return _overlay(k, f"WMA {period}", color)

    @staticmethod
    def dema(period: int = 20, *, color: str = "#AB47BC",
             key: Optional[str] = None) -> SeriesDef:
        """Double EMA."""
        k = key or f"dema{period}"
        return _overlay(k, f"DEMA {period}", color)

    @staticmethod
    def tema(period: int = 20, *, color: str = "#7B1FA2",
             key: Optional[str] = None) -> SeriesDef:
        """Triple EMA."""
        k = key or f"tema{period}"
        return _overlay(k, f"TEMA {period}", color)

    @staticmethod
    def hma(period: int = 20, *, color: str = "#00BCD4",
            key: Optional[str] = None) -> SeriesDef:
        """Hull Moving Average."""
        k = key or f"hma{period}"
        return _overlay(k, f"HMA {period}", color)

    @staticmethod
    def zlema(period: int = 20, *, color: str = "#4CAF50",
              key: Optional[str] = None) -> SeriesDef:
        """Zero-Lag EMA."""
        k = key or f"zlema{period}"
        return _overlay(k, f"ZLEMA {period}", color)

    @staticmethod
    def kama(period: int = 10, *, color: str = "#FF5722",
             key: Optional[str] = None) -> SeriesDef:
        """Kaufman Adaptive Moving Average."""
        k = key or f"kama{period}"
        return _overlay(k, f"KAMA {period}", color)

    # ── Price channels / envelopes ───────────────────────────────────

    @staticmethod
    def bollinger(period: int = 20, std: float = 2.0,
                  key_prefix: str = "bb") -> list[SeriesDef]:
        """Bollinger Bands — returns [upper, mid, lower]."""
        p = f"{key_prefix}_pane"
        c = "rgba(100,120,220,.55)"
        return [
            _overlay(f"{key_prefix}_upper", f"BB Upper ({period},{std})", c,
                     pane_id=p, style=2),
            _overlay(f"{key_prefix}_mid",   f"BB Mid ({period})",         c,
                     pane_id=p, style=1),
            _overlay(f"{key_prefix}_lower", f"BB Lower ({period},{std})", c,
                     pane_id=p, style=2),
        ]

    @staticmethod
    def keltner(period: int = 20, mult: float = 2.0,
                key_prefix: str = "kc") -> list[SeriesDef]:
        """Keltner Channel — returns [upper, mid, lower]."""
        p = f"{key_prefix}_pane"
        return [
            _overlay(f"{key_prefix}_upper", f"KC Upper ({period},{mult})", "#9C27B0",
                     pane_id=p, style=2),
            _overlay(f"{key_prefix}_mid",   f"KC Mid ({period})",          "#9C27B0",
                     pane_id=p, style=1),
            _overlay(f"{key_prefix}_lower", f"KC Lower ({period},{mult})", "#9C27B0",
                     pane_id=p, style=2),
        ]

    @staticmethod
    def donchian(period: int = 20, key_prefix: str = "dc") -> list[SeriesDef]:
        """Donchian Channel — returns [upper, mid, lower]."""
        p = f"{key_prefix}_pane"
        return [
            _overlay(f"{key_prefix}_upper", f"DC Upper ({period})", "#FF5722",
                     pane_id=p, style=2),
            _overlay(f"{key_prefix}_mid",   f"DC Mid ({period})",   "#FF5722",
                     pane_id=p, style=1),
            _overlay(f"{key_prefix}_lower", f"DC Lower ({period})", "#FF5722",
                     pane_id=p, style=2),
        ]

    @staticmethod
    def envelope(period: int = 20, pct: float = 2.5,
                 key_prefix: str = "env") -> list[SeriesDef]:
        """Price Envelope — returns [upper, mid, lower]."""
        p = f"{key_prefix}_pane"
        return [
            _overlay(f"{key_prefix}_upper", f"Env Upper ({period},{pct}%)", "#795548",
                     pane_id=p, style=2),
            _overlay(f"{key_prefix}_mid",   f"Env Mid ({period})",           "#795548",
                     pane_id=p, style=1),
            _overlay(f"{key_prefix}_lower", f"Env Lower ({period},{pct}%)", "#795548",
                     pane_id=p, style=2),
        ]

    # ── Advanced overlays ────────────────────────────────────────────

    @staticmethod
    def vwap(*, color: str = "#FCD535") -> SeriesDef:
        """Volume-Weighted Average Price."""
        return _overlay("vwap", "VWAP", color, width=2)

    @staticmethod
    def vwma(period: int = 20, *, color: str = "#FF5722") -> SeriesDef:
        """Volume-Weighted Moving Average."""
        return _overlay(f"vwma{period}", f"VWMA {period}", color)

    @staticmethod
    def supertrend(period: int = 10, mult: float = 3.0) -> SeriesDef:
        """
        SuperTrend.

        Push per-point color to show direction:
        - ``"#089981"`` when bullish
        - ``"#F23645"`` when bearish
        """
        return _overlay(f"st_{period}_{mult}",
                        f"SuperTrend ({period},{mult})", "#089981")

    @staticmethod
    def psar(step: float = 0.02, max_step: float = 0.2) -> SeriesDef:
        """Parabolic SAR (scatter plot)."""
        return SeriesDef(key="psar", label=f"PSAR ({step},{max_step})",
                         pane="main", kind="scatter", color="#FF9800",
                         pane_id="psar")

    @staticmethod
    def ichimoku(key_prefix: str = "ichi") -> list[SeriesDef]:
        """Ichimoku Cloud — returns [tenkan, kijun, senkou_a, senkou_b, chikou]."""
        p = key_prefix
        return [
            _overlay(f"{p}_tenkan",   "Tenkan-sen",  "#F44336"),
            _overlay(f"{p}_kijun",    "Kijun-sen",   "#2196F3"),
            _overlay(f"{p}_senkou_a", "Senkou A",    "#089981"),
            _overlay(f"{p}_senkou_b", "Senkou B",    "#F23645"),
            _overlay(f"{p}_chikou",   "Chikou Span", "#9C27B0", style=1),
        ]

    @staticmethod
    def linear_reg(period: int = 14, *, color: str = "#FF9800") -> SeriesDef:
        """Linear Regression curve."""
        return _overlay(f"linreg{period}", f"LinReg ({period})", color, style=2)

    @staticmethod
    def pivot_points(key_prefix: str = "pp") -> list[SeriesDef]:
        """
        Classic Pivot Points — returns [R3, R2, R1, PP, S1, S2, S3].

        Push horizontal line data (one point each, same time range).
        """
        p = f"{key_prefix}_pane"
        levels = [
            (f"{key_prefix}_r3", "R3", "#F23645"),
            (f"{key_prefix}_r2", "R2", "#EF9A9A"),
            (f"{key_prefix}_r1", "R1", "#FFCDD2"),
            (f"{key_prefix}_pp", "PP", "#FCD535"),
            (f"{key_prefix}_s1", "S1", "#C8E6C9"),
            (f"{key_prefix}_s2", "S2", "#81C784"),
            (f"{key_prefix}_s3", "S3", "#089981"),
        ]
        return [_overlay(k, l, c, pane_id=p, style=2) for k, l, c in levels]


# ══════════════════════════════════════════════════════════════════════
# Oscillators  (rendered in a separate sub-pane below the chart)
# ══════════════════════════════════════════════════════════════════════

class Oscillator:
    """SeriesDef factories for sub-pane oscillators."""

    @staticmethod
    def rsi(period: int = 14, *, color: str = "#AB47BC") -> SeriesDef:
        """Relative Strength Index."""
        return _sub(f"rsi{period}", f"RSI ({period})", color,
                    pane_id=f"pane_rsi{period}",
                    levels=_rsi_levels(), height=100)

    @staticmethod
    def macd(fast: int = 12, slow: int = 26, signal: int = 9,
             key_prefix: str = "macd") -> list[SeriesDef]:
        """MACD — returns [line, signal, histogram]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_line",   f"MACD ({fast},{slow})", "#42A5F5", p),
            _sub(f"{key_prefix}_signal", f"Signal ({signal})",    "#FFA726", p),
            _hist(f"{key_prefix}_hist",  "Histogram",              p),
        ]

    @staticmethod
    def stochastic(k: int = 14, smooth_k: int = 3, d: int = 3,
                   key_prefix: str = "stoch") -> list[SeriesDef]:
        """Stochastic Oscillator — returns [%K, %D]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_k", f"%K ({k})", "#2962FF", p, levels=_stoch_levels()),
            _sub(f"{key_prefix}_d", f"%D ({d})", "#FF6D00", p),
        ]

    @staticmethod
    def stoch_rsi(rsi_len: int = 14, stoch_len: int = 14,
                  smooth_k: int = 3, smooth_d: int = 3,
                  key_prefix: str = "srsi") -> list[SeriesDef]:
        """Stochastic RSI — returns [%K, %D]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_k", "StochRSI %K", "#F44336", p, levels=_stoch_levels()),
            _sub(f"{key_prefix}_d", "StochRSI %D", "#2196F3", p),
        ]

    @staticmethod
    def cci(period: int = 20, *, color: str = "#9C27B0") -> SeriesDef:
        """Commodity Channel Index."""
        lvls = [Level(100, "#EF5350", 2, "OB"), Level(-100, "#26A69A", 2, "OS")]
        return _sub(f"cci{period}", f"CCI ({period})", color,
                    pane_id=f"pane_cci{period}", levels=lvls)

    @staticmethod
    def williams_r(period: int = 14, *, color: str = "#00BCD4") -> SeriesDef:
        """Williams %R."""
        lvls = [Level(-20, "#EF5350", 2, "OB"), Level(-80, "#26A69A", 2, "OS")]
        return _sub(f"willr{period}", f"Williams %R ({period})", color,
                    pane_id=f"pane_willr{period}", digits=1, levels=lvls)

    @staticmethod
    def atr(period: int = 14, *, color: str = "#B71C1C") -> SeriesDef:
        """Average True Range."""
        return _sub(f"atr{period}", f"ATR ({period})", color,
                    pane_id=f"pane_atr{period}", digits=4, height=80)

    @staticmethod
    def adx(period: int = 14, key_prefix: str = "adx") -> list[SeriesDef]:
        """Average Directional Index — returns [ADX, +DI, -DI]."""
        p = f"{key_prefix}_pane"
        lvls = [Level(25, "#787B86", 2, "Trend")]
        return [
            _sub(f"{key_prefix}",       f"ADX ({period})", "#2196F3", p, levels=lvls),
            _sub(f"{key_prefix}_plus",  "+DI",             "#089981", p),
            _sub(f"{key_prefix}_minus", "-DI",             "#F23645", p),
        ]

    @staticmethod
    def aroon(period: int = 25, key_prefix: str = "aroon") -> list[SeriesDef]:
        """Aroon — returns [up, down]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_up",   f"Aroon Up ({period})",   "#26A69A", p),
            _sub(f"{key_prefix}_down", f"Aroon Down ({period})", "#EF5350", p),
        ]

    @staticmethod
    def momentum(period: int = 10, *, color: str = "#FF5722") -> SeriesDef:
        """Momentum."""
        return _sub(f"mom{period}", f"Momentum ({period})", color,
                    pane_id=f"pane_mom{period}", digits=4, height=80)

    @staticmethod
    def roc(period: int = 12, *, color: str = "#00BCD4") -> SeriesDef:
        """Rate of Change (%)."""
        return _sub(f"roc{period}", f"ROC ({period})%", color,
                    pane_id=f"pane_roc{period}")

    @staticmethod
    def trix(period: int = 15, *, color: str = "#E91E63") -> SeriesDef:
        """TRIX — triple-smoothed EMA ROC."""
        return _sub(f"trix{period}", f"TRIX ({period})", color,
                    pane_id=f"pane_trix{period}")

    @staticmethod
    def dpo(period: int = 20, *, color: str = "#607D8B") -> SeriesDef:
        """Detrended Price Oscillator."""
        return _sub(f"dpo{period}", f"DPO ({period})", color,
                    pane_id=f"pane_dpo{period}")

    @staticmethod
    def cmo(period: int = 14, *, color: str = "#795548") -> SeriesDef:
        """Chande Momentum Oscillator."""
        lvls = [Level(50, "#EF5350", 2, "OB"), Level(-50, "#26A69A", 2, "OS")]
        return _sub(f"cmo{period}", f"CMO ({period})", color,
                    pane_id=f"pane_cmo{period}", levels=lvls)

    @staticmethod
    def ppo(fast: int = 12, slow: int = 26, signal: int = 9,
            key_prefix: str = "ppo") -> list[SeriesDef]:
        """Percentage Price Oscillator — returns [line, signal, histogram]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_line",   f"PPO ({fast},{slow})", "#42A5F5", p),
            _sub(f"{key_prefix}_signal", f"Signal ({signal})",   "#FFA726", p),
            _hist(f"{key_prefix}_hist",  "Histogram",             p),
        ]

    @staticmethod
    def awesome_oscillator(key: str = "ao") -> SeriesDef:
        """
        Awesome Oscillator (histogram).

        Push per-point color:
        - ``"#089981"`` when value ≥ 0 (or rising)
        - ``"#F23645"`` when value < 0 (or falling)
        """
        return _hist(key, "Awesome Oscillator", "pane_ao")

    @staticmethod
    def ultimate_oscillator(key: str = "uo") -> SeriesDef:
        """Ultimate Oscillator."""
        lvls = [Level(70, "#EF5350", 2, "OB"), Level(30, "#26A69A", 2, "OS")]
        return _sub(key, "Ultimate Oscillator", "#9C27B0",
                    pane_id="pane_uo", levels=lvls)

    @staticmethod
    def mass_index(key: str = "mi") -> SeriesDef:
        """Mass Index."""
        lvls = [Level(27, "#EF5350", 2, "Bulge"), Level(26.5, "#26A69A", 2, "Reversal")]
        return _sub(key, "Mass Index", "#607D8B", pane_id="pane_mi", levels=lvls)

    @staticmethod
    def dmi(period: int = 14, key_prefix: str = "dmi") -> list[SeriesDef]:
        """Directional Movement Index — returns [+DI, -DI]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_plus",  f"+DI ({period})", "#089981", p),
            _sub(f"{key_prefix}_minus", f"-DI ({period})", "#F23645", p),
        ]

    @staticmethod
    def vortex(period: int = 14, key_prefix: str = "vortex") -> list[SeriesDef]:
        """Vortex Indicator — returns [VI+, VI-]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_pos", f"VI+ ({period})", "#089981", p),
            _sub(f"{key_prefix}_neg", f"VI- ({period})", "#F23645", p),
        ]

    @staticmethod
    def kst(key_prefix: str = "kst") -> list[SeriesDef]:
        """Know Sure Thing — returns [KST, signal]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}",        "KST",    "#2196F3", p),
            _sub(f"{key_prefix}_signal", "Signal", "#FFA726", p),
        ]

    @staticmethod
    def elder_ray(key_prefix: str = "er") -> list[SeriesDef]:
        """Elder Ray — returns [bull_power, bear_power]."""
        p = f"{key_prefix}_pane"
        return [
            _hist(f"{key_prefix}_bull", "Bull Power", p, up="#089981", dn="#089981"),
            _hist(f"{key_prefix}_bear", "Bear Power", p, up="#F23645", dn="#F23645"),
        ]

    @staticmethod
    def squeeze_momentum(key_prefix: str = "sq") -> SeriesDef:
        """
        Squeeze Momentum (LazyBear style).

        Push per-point color to show momentum direction:
        - lime = increasing positive momentum
        - green = decreasing positive momentum
        - red = increasing negative momentum
        - maroon = decreasing negative momentum
        """
        return _hist(key_prefix, "Squeeze Momentum", "pane_sq")

    @staticmethod
    def fisher(period: int = 9, key_prefix: str = "fisher") -> list[SeriesDef]:
        """Fisher Transform — returns [fisher, signal]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}",        f"Fisher ({period})", "#2196F3", p),
            _sub(f"{key_prefix}_signal", "Signal",             "#FFA726", p),
        ]

    @staticmethod
    def ehlers_stochastic(key_prefix: str = "esf") -> list[SeriesDef]:
        """Ehlers Fisher Stochastic — returns [value, trigger]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}_val", "ESF",     "#2196F3", p),
            _sub(f"{key_prefix}_trg", "Trigger", "#FFA726", p),
        ]


# ══════════════════════════════════════════════════════════════════════
# Volume indicators
# ══════════════════════════════════════════════════════════════════════

class Volume:
    """SeriesDef factories for volume-based indicators."""

    @staticmethod
    def bars(up: str = "#08998166", down: str = "#F2364566") -> SeriesDef:
        """
        Volume bars with bull/bear coloring.

        Push per-point color from your data::

            points = [
                Point(bar.time, bar.volume,
                      "#08998166" if bar.close >= bar.open else "#F2364566")
                for bar in candles
            ]
        """
        return SeriesDef(
            key="volume", label="Volume",
            pane="sub", kind="histogram",
            color=up, color_pos=up, color_neg=down,
            digits=0, pane_id="volume_pane", pane_height=60,
            margins={"top": 0.8, "bottom": 0.0},
            price_line=False, last_value=False,
        )

    @staticmethod
    def obv(*, color: str = "#2196F3") -> SeriesDef:
        """On-Balance Volume."""
        return _sub("obv", "OBV", color, pane_id="pane_obv", digits=0)

    @staticmethod
    def mfi(period: int = 14, *, color: str = "#4CAF50") -> SeriesDef:
        """Money Flow Index."""
        lvls = [Level(80, "#EF5350", 2, "OB"), Level(20, "#26A69A", 2, "OS")]
        return _sub(f"mfi{period}", f"MFI ({period})", color,
                    pane_id=f"pane_mfi{period}", levels=lvls)

    @staticmethod
    def cmf(period: int = 20, *, color: str = "#00BCD4") -> SeriesDef:
        """Chaikin Money Flow."""
        return _sub(f"cmf{period}", f"CMF ({period})", color,
                    pane_id=f"pane_cmf{period}", digits=3, height=80)

    @staticmethod
    def vpt(*, color: str = "#9C27B0") -> SeriesDef:
        """Volume Price Trend."""
        return _sub("vpt", "VPT", color, pane_id="pane_vpt", digits=0)

    @staticmethod
    def nvi(*, color: str = "#FF5722") -> SeriesDef:
        """Negative Volume Index."""
        return _sub("nvi", "NVI", color, pane_id="pane_nvi", digits=0)

    @staticmethod
    def pvi(*, color: str = "#4CAF50") -> SeriesDef:
        """Positive Volume Index."""
        return _sub("pvi", "PVI", color, pane_id="pane_pvi", digits=0)

    @staticmethod
    def volume_sma(period: int = 20, *, color: str = "#FF9800") -> SeriesDef:
        """
        SMA of volume — overlaid on the volume bars.

        Render on the same pane as Volume.bars() by keeping pane_id="volume_pane".
        """
        return SeriesDef(
            key=f"vsma{period}", label=f"Vol SMA {period}",
            pane="sub", kind="line", color=color,
            pane_id="volume_pane", pane_height=60,
            margins={"top": 0.8, "bottom": 0.0},
        )

    @staticmethod
    def chaikin_oscillator(fast: int = 3, slow: int = 10,
                            key: str = "cho") -> SeriesDef:
        """Chaikin Oscillator."""
        return _sub(key, f"Chaikin Osc ({fast},{slow})", "#2196F3",
                    pane_id="pane_cho")

    @staticmethod
    def ease_of_movement(period: int = 14, *, color: str = "#607D8B") -> SeriesDef:
        """Ease of Movement."""
        return _sub(f"eom{period}", f"EoM ({period})", color,
                    pane_id=f"pane_eom{period}")

    @staticmethod
    def force_index(period: int = 13, *, color: str = "#E91E63") -> SeriesDef:
        """Elder Force Index."""
        return _sub(f"fi{period}", f"Force Index ({period})", color,
                    pane_id=f"pane_fi{period}")

    @staticmethod
    def klinger(key_prefix: str = "kvo") -> list[SeriesDef]:
        """Klinger Volume Oscillator — returns [KVO, signal]."""
        p = f"{key_prefix}_pane"
        return [
            _sub(f"{key_prefix}",        "KVO",    "#2196F3", p),
            _sub(f"{key_prefix}_signal", "Signal", "#FFA726", p),
        ]


# ══════════════════════════════════════════════════════════════════════
# Volatility indicators
# ══════════════════════════════════════════════════════════════════════

class Volatility:
    """SeriesDef factories for volatility indicators."""

    @staticmethod
    def atr(period: int = 14, *, color: str = "#B71C1C") -> SeriesDef:
        """Average True Range."""
        return _sub(f"atr{period}", f"ATR ({period})", color,
                    pane_id=f"pane_atr{period}", digits=4, height=80)

    @staticmethod
    def natr(period: int = 14, *, color: str = "#E53935") -> SeriesDef:
        """Normalised ATR (%)."""
        return _sub(f"natr{period}", f"NATR ({period})", color,
                    pane_id=f"pane_natr{period}", digits=3, height=80)

    @staticmethod
    def historical_volatility(period: int = 20, *, color: str = "#7B1FA2") -> SeriesDef:
        """Historical Volatility (annualised %)."""
        return _sub(f"hv{period}", f"HV {period}", color,
                    pane_id=f"pane_hv{period}", digits=2)

    @staticmethod
    def std_dev(period: int = 20, *, color: str = "#9C27B0") -> SeriesDef:
        """Rolling Standard Deviation."""
        return _sub(f"std{period}", f"StdDev {period}", color,
                    pane_id=f"pane_std{period}", digits=4)

    @staticmethod
    def chaikin_volatility(key: str = "cv") -> SeriesDef:
        """Chaikin Volatility."""
        return _sub(key, "Chaikin Volatility", "#FF9800",
                    pane_id="pane_cv", digits=2)

    @staticmethod
    def ulcer_index(period: int = 14, *, color: str = "#795548") -> SeriesDef:
        """Ulcer Index (downside volatility)."""
        return _sub(f"ui{period}", f"Ulcer Index ({period})", color,
                    pane_id=f"pane_ui{period}", digits=3)

    @staticmethod
    def vix_fix(key: str = "vixfix") -> SeriesDef:
        """VIX Fix (synthetic VIX for any asset)."""
        return _sub(key, "VIX Fix", "#F44336",
                    pane_id="pane_vixfix", digits=2)
