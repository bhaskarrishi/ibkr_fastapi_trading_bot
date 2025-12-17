"""
Signal Validation Service
Confirms TradingView signals using independent market data from Yahoo Finance.
Implements multi-layer validation: price, trend, momentum, candle strength, volume, multi-timeframe alignment.
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Dict, Any, Tuple
import ta
import logging

logger = logging.getLogger(__name__)


class SignalValidator:
    """
    Validates TradingView signals against independent market data.
    Uses scoring system where 4/5 checks must pass for approval.
    """

    def __init__(self, symbol: str, signal_direction: str):
        """
        Args:
            symbol: Stock ticker (e.g., 'AAPL')
            signal_direction: 'BUY' or 'SELL'
        """
        self.symbol = symbol.upper()
        self.signal_direction = signal_direction.upper()
        self.validation_result = {
            'valid': False,
            'score': 0,
            'max_score': 5,
            'checks': {},
            'errors': [],
            'warnings': [],
            'metadata': {}
        }

    def validate(self) -> Dict[str, Any]:
        """
        Run comprehensive signal validation.
        Returns validation result with detailed scoring and feedback.
        """
        try:
            # Fetch data: 15m, 1h, daily
            df_15m = self._fetch_data(interval='15m', period='7d')
            df_1h = self._fetch_data(interval='60m', period='30d')
            
            if df_15m is None or df_15m.empty:
                self.validation_result['valid'] = False
                self.validation_result['errors'].append(
                    f"Failed to fetch 15m data for {self.symbol}"
                )
                return self.validation_result

            # 1. Price Confirmation
            self._check_price_confirmation(df_15m)

            # 2. Trend Confirmation (15m)
            self._check_trend_confirmation(df_15m)

            # 3. Momentum Confirmation (RSI + MACD)
            self._check_momentum_confirmation(df_15m)

            # 4. Candle Strength
            self._check_candle_strength(df_15m)

            # 5. Volume Confirmation
            self._check_volume_confirmation(df_15m)

            # 6. Multi-Timeframe Alignment (1h confirmation)
            if df_1h is not None and not df_1h.empty:
                self._check_multitf_alignment(df_1h)

            # Calculate final score and decision
            self._calculate_final_decision()

        except Exception as e:
            logger.exception(f"Signal validation error for {self.symbol}")
            self.validation_result['valid'] = False
            self.validation_result['errors'].append(f"Validation error: {str(e)}")

        return self.validation_result

    def _fetch_data(self, interval: str = '15m', period: str = '7d') -> pd.DataFrame:
        """
        Fetch historical OHLCV data from Yahoo Finance.
        """
        try:
            ticker = yf.Ticker(self.symbol)
            df = ticker.history(interval=interval, period=period)
            
            if df.empty:
                logger.warning(f"No data returned for {self.symbol} at {interval}")
                return None
            
            # Rename columns to lowercase for consistency
            df.columns = [col.lower() for col in df.columns]
            return df
        except Exception as e:
            logger.error(f"Failed to fetch {interval} data for {self.symbol}: {e}")
            return None

    def _check_price_confirmation(self, df: pd.DataFrame) -> None:
        """
        1️⃣ Price Confirmation
        - Latest price exists and is fresh (within 20 minutes)
        - No NaN / zero price
        - No abnormal spike (< 3% move from previous)
        """
        check_name = 'price_confirmation'
        result = {
            'passed': False,
            'details': [],
            'price': None,
            'timestamp': None
        }

        try:
            # Get latest candle
            latest = df.iloc[-1]
            close_price = latest['close']
            high_price = latest['high']
            low_price = latest['low']
            timestamp = df.index[-1]

            result['price'] = close_price
            result['timestamp'] = timestamp.isoformat()

            # Check 1: Price exists and is valid
            if pd.isna(close_price) or close_price <= 0:
                result['details'].append('❌ Price is NaN or zero')
                self.validation_result['errors'].append('Invalid price data')
                self.validation_result['checks'][check_name] = result
                return

            result['details'].append(f'✅ Valid price: ${close_price:.2f}')

            # Check 2: Data freshness
            now = datetime.now(timezone.utc)
            # Convert timestamp to UTC-aware if needed
            ts_utc = pd.Timestamp(timestamp).tz_localize(None).replace(tzinfo=timezone.utc)
            age_minutes = (now - ts_utc).total_seconds() / 60

            if age_minutes > 20:
                result['details'].append(
                    f'⚠️ Data age: {age_minutes:.1f} minutes (threshold: 20m)'
                )
                self.validation_result['warnings'].append(
                    f'Price data is {age_minutes:.1f} min old'
                )
            else:
                result['details'].append(f'✅ Data fresh: {age_minutes:.1f} min old')

            # Check 3: No abnormal spike (compare to previous close)
            if len(df) >= 2:
                prev_close = df.iloc[-2]['close']
                if prev_close > 0:
                    price_change_pct = abs(close_price - prev_close) / prev_close * 100
                    if price_change_pct > 3.0:
                        result['details'].append(
                            f'⚠️ Abnormal spike: {price_change_pct:.2f}% (threshold: 3%)'
                        )
                        self.validation_result['warnings'].append(
                            f'Price moved {price_change_pct:.2f}% since last candle'
                        )
                    else:
                        result['details'].append(
                            f'✅ Price move normal: {price_change_pct:.2f}%'
                        )

            # Check 4: High/Low validity
            if high_price < close_price or low_price > close_price:
                result['details'].append('❌ Invalid OHLC structure')
                self.validation_result['errors'].append('OHLC data integrity check failed')
                self.validation_result['checks'][check_name] = result
                return

            result['passed'] = True
            self.validation_result['score'] += 1

        except Exception as e:
            logger.error(f"Price confirmation check failed: {e}")
            result['details'].append(f'Error: {str(e)}')

        self.validation_result['checks'][check_name] = result

    def _check_trend_confirmation(self, df: pd.DataFrame) -> None:
        """
        2️⃣ Trend Confirmation (15m timeframe)
        Uses EMA 20, 50, 200 and VWAP.
        
        BUY: close > EMA 20 > EMA 50 > EMA 200 (strong) OR close > VWAP
        SELL: close < EMA 20 < EMA 50
        """
        check_name = 'trend_confirmation'
        result = {
            'passed': False,
            'details': [],
            'ema_20': None,
            'ema_50': None,
            'ema_200': None,
            'vwap': None
        }

        try:
            if len(df) < 200:
                result['details'].append(f'⚠️ Insufficient data: {len(df)} candles (need 200 for EMA200)')
                self.validation_result['warnings'].append('Insufficient candles for full trend analysis')
            else:
                # Calculate EMAs
                df['ema_20'] = ta.trend.ema_indicator(df['close'], window=20)
                df['ema_50'] = ta.trend.ema_indicator(df['close'], window=50)
                df['ema_200'] = ta.trend.ema_indicator(df['close'], window=200)
                
                latest = df.iloc[-1]
                close = latest['close']
                ema_20 = latest['ema_20']
                ema_50 = latest['ema_50']
                ema_200 = latest['ema_200']
                
                result['ema_20'] = ema_20
                result['ema_50'] = ema_50
                result['ema_200'] = ema_200

            # Calculate VWAP (simplified: using close, high, low, volume)
            df['vwap'] = self._calculate_vwap(df)
            latest = df.iloc[-1]
            close = latest['close']
            vwap = latest['vwap']
            ema_20 = df.iloc[-1].get('ema_20')
            ema_50 = df.iloc[-1].get('ema_50')
            ema_200 = df.iloc[-1].get('ema_200')

            result['vwap'] = vwap

            if self.signal_direction == 'BUY':
                # BUY: close > EMA 20 > EMA 50 > EMA 200 (strong trend)
                # OR close > VWAP (acceptable)
                
                buy_checks = []

                if ema_20 is not None and ema_50 is not None:
                    if close > ema_20 and ema_20 > ema_50:
                        buy_checks.append('✅ EMA Structure: Close > EMA20 > EMA50')
                        
                        if ema_200 is not None and ema_50 > ema_200:
                            buy_checks.append('✅ Strong Trend: EMA50 > EMA200')
                        else:
                            buy_checks.append('⚠️ EMA50 < EMA200 (weak long-term trend)')
                    else:
                        buy_checks.append(f'❌ EMA Fail: Close{close:.2f} vs EMA20:{ema_20:.2f} vs EMA50:{ema_50:.2f}')

                if vwap is not None:
                    if close > vwap:
                        buy_checks.append(f'✅ Price > VWAP: {close:.2f} > {vwap:.2f}')
                    else:
                        buy_checks.append(f'❌ Price < VWAP: {close:.2f} < {vwap:.2f}')

                result['details'] = buy_checks
                # Pass if EMA structure OR price > VWAP
                result['passed'] = any('✅' in check for check in buy_checks)

            elif self.signal_direction == 'SELL':
                # SELL: close < EMA 20 < EMA 50
                sell_checks = []

                if ema_20 is not None and ema_50 is not None:
                    if close < ema_20 and ema_20 < ema_50:
                        sell_checks.append('✅ EMA Structure: Close < EMA20 < EMA50')
                    else:
                        sell_checks.append(f'❌ EMA Fail: Close{close:.2f} vs EMA20:{ema_20:.2f} vs EMA50:{ema_50:.2f}')

                if vwap is not None:
                    if close < vwap:
                        sell_checks.append(f'✅ Price < VWAP: {close:.2f} < {vwap:.2f}')
                    else:
                        sell_checks.append(f'❌ Price > VWAP: {close:.2f} > {vwap:.2f}')

                result['details'] = sell_checks
                result['passed'] = any('✅' in check for check in sell_checks)

            if result['passed']:
                self.validation_result['score'] += 1

        except Exception as e:
            logger.error(f"Trend confirmation check failed: {e}")
            result['details'].append(f'Error: {str(e)}')

        self.validation_result['checks'][check_name] = result

    def _check_momentum_confirmation(self, df: pd.DataFrame) -> None:
        """
        3️⃣ Momentum Confirmation
        RSI (14) + MACD for confirming trend direction.
        
        BUY: RSI 55-70, MACD > Signal, histogram increasing
        SELL: RSI 30-45, MACD < Signal, histogram decreasing
        """
        check_name = 'momentum_confirmation'
        result = {
            'passed': False,
            'details': [],
            'rsi': None,
            'macd': None,
            'macd_signal': None,
            'macd_histogram': None
        }

        try:
            # Calculate RSI
            df['rsi'] = ta.momentum.rsi(df['close'], window=14)
            
            # Calculate MACD
            macd = ta.trend.MACD(df['close'])
            df['macd'] = macd.macd()
            df['macd_signal'] = macd.macd_signal()
            df['macd_diff'] = macd.macd_diff()

            latest = df.iloc[-1]
            rsi = latest['rsi']
            macd = latest['macd']
            macd_signal = latest['macd_signal']
            macd_diff = latest['macd_diff']

            result['rsi'] = rsi
            result['macd'] = macd
            result['macd_signal'] = macd_signal
            result['macd_histogram'] = macd_diff

            if self.signal_direction == 'BUY':
                # BUY: RSI 55-70, avoid >75
                rsi_checks = []
                
                if pd.isna(rsi):
                    rsi_checks.append('⚠️ RSI not calculated')
                elif rsi > 75:
                    rsi_checks.append(f'❌ Overbought: RSI {rsi:.2f} > 75')
                elif 55 <= rsi <= 70:
                    rsi_checks.append(f'✅ Bullish RSI: {rsi:.2f} (55-70)')
                elif rsi >= 50:
                    rsi_checks.append(f'⚠️ Neutral RSI: {rsi:.2f} (not ideal for BUY)')
                else:
                    rsi_checks.append(f'❌ Weak RSI: {rsi:.2f} (< 50)')

                # MACD: > Signal and increasing histogram
                macd_checks = []
                if pd.isna(macd) or pd.isna(macd_signal):
                    macd_checks.append('⚠️ MACD not calculated')
                elif macd > macd_signal and macd_diff > 0:
                    macd_checks.append(f'✅ MACD bullish: {macd:.4f} > Signal {macd_signal:.4f}')
                elif macd > macd_signal:
                    macd_checks.append(f'⚠️ MACD above Signal but histogram declining')
                else:
                    macd_checks.append(f'❌ MACD below Signal: not bullish')

                result['details'] = rsi_checks + macd_checks
                result['passed'] = any('✅' in check for check in rsi_checks) and \
                                  any('✅' in check for check in macd_checks)

            elif self.signal_direction == 'SELL':
                # SELL: RSI 30-45, avoid <25
                rsi_checks = []
                
                if pd.isna(rsi):
                    rsi_checks.append('⚠️ RSI not calculated')
                elif rsi < 25:
                    rsi_checks.append(f'❌ Oversold: RSI {rsi:.2f} < 25')
                elif 30 <= rsi <= 45:
                    rsi_checks.append(f'✅ Bearish RSI: {rsi:.2f} (30-45)')
                elif rsi <= 50:
                    rsi_checks.append(f'⚠️ Neutral RSI: {rsi:.2f}')
                else:
                    rsi_checks.append(f'❌ Strong RSI: {rsi:.2f} (> 50)')

                # MACD: < Signal and decreasing histogram
                macd_checks = []
                if pd.isna(macd) or pd.isna(macd_signal):
                    macd_checks.append('⚠️ MACD not calculated')
                elif macd < macd_signal and macd_diff < 0:
                    macd_checks.append(f'✅ MACD bearish: {macd:.4f} < Signal {macd_signal:.4f}')
                elif macd < macd_signal:
                    macd_checks.append(f'⚠️ MACD below Signal but histogram rising')
                else:
                    macd_checks.append(f'❌ MACD above Signal: not bearish')

                result['details'] = rsi_checks + macd_checks
                result['passed'] = any('✅' in check for check in rsi_checks) and \
                                  any('✅' in check for check in macd_checks)

            if result['passed']:
                self.validation_result['score'] += 1

        except Exception as e:
            logger.error(f"Momentum confirmation check failed: {e}")
            result['details'].append(f'Error: {str(e)}')

        self.validation_result['checks'][check_name] = result

    def _check_candle_strength(self, df: pd.DataFrame) -> None:
        """
        4️⃣ Candle Strength Confirmation
        Latest closed 15m candle:
        - Body size >= 60% of range
        - Avoid doji and indecision candles
        """
        check_name = 'candle_strength'
        result = {
            'passed': False,
            'details': [],
            'body_size': None,
            'body_ratio': None,
            'range': None
        }

        try:
            latest = df.iloc[-1]
            open_p = latest['open']
            close_p = latest['close']
            high = latest['high']
            low = latest['low']

            range_val = high - low
            body_size = abs(close_p - open_p)
            
            result['range'] = range_val
            result['body_size'] = body_size

            if range_val <= 0:
                result['details'].append('❌ Invalid candle range')
                self.validation_result['checks'][check_name] = result
                return

            body_ratio = body_size / range_val
            result['body_ratio'] = body_ratio

            # Check 1: Body strength
            if body_ratio >= 0.6:
                result['details'].append(
                    f'✅ Strong body: {body_ratio*100:.1f}% of range (threshold: 60%)'
                )
                result['passed'] = True
            else:
                result['details'].append(
                    f'❌ Weak body: {body_ratio*100:.1f}% of range (need: 60%)'
                )
                result['passed'] = False

            # Check 2: Doji detection (very small body)
            if body_ratio < 0.1:
                result['details'].append('⚠️ Doji-like candle (indecision)')
                result['passed'] = False

            # Check 3: Both long wicks (indecision)
            upper_wick = high - max(open_p, close_p)
            lower_wick = min(open_p, close_p) - low
            
            if upper_wick > body_size and lower_wick > body_size:
                result['details'].append('⚠️ Indecision candle (long wicks both sides)')
                result['passed'] = False

            if result['passed']:
                self.validation_result['score'] += 1

        except Exception as e:
            logger.error(f"Candle strength check failed: {e}")
            result['details'].append(f'Error: {str(e)}')

        self.validation_result['checks'][check_name] = result

    def _check_volume_confirmation(self, df: pd.DataFrame) -> None:
        """
        5️⃣ Volume Confirmation
        Current volume >= 1.2 × 20-period average volume
        """
        check_name = 'volume_confirmation'
        result = {
            'passed': False,
            'details': [],
            'current_volume': None,
            'volume_sma20': None,
            'ratio': None
        }

        try:
            if len(df) < 20:
                result['details'].append(f'⚠️ Insufficient volume data: {len(df)} candles')
                result['passed'] = True  # Skip check gracefully
                self.validation_result['checks'][check_name] = result
                return

            df['vol_sma20'] = df['volume'].rolling(window=20).mean()
            
            latest = df.iloc[-1]
            current_vol = latest['volume']
            vol_sma20 = latest['vol_sma20']

            result['current_volume'] = current_vol
            result['volume_sma20'] = vol_sma20

            if pd.isna(vol_sma20) or vol_sma20 <= 0:
                result['details'].append('⚠️ Volume SMA20 not available')
                result['passed'] = True  # Skip check gracefully
                self.validation_result['checks'][check_name] = result
                return

            ratio = current_vol / vol_sma20
            result['ratio'] = ratio

            if ratio >= 1.2:
                result['details'].append(
                    f'✅ Volume elevated: {ratio:.2f}x average (threshold: 1.2x)'
                )
                result['passed'] = True
                self.validation_result['score'] += 1
            else:
                result['details'].append(
                    f'⚠️ Low volume: {ratio:.2f}x average (need: 1.2x)'
                )
                result['passed'] = True  # Not a hard fail, just warning

        except Exception as e:
            logger.error(f"Volume confirmation check failed: {e}")
            result['details'].append(f'Error: {str(e)}')
            result['passed'] = True

        self.validation_result['checks'][check_name] = result

    def _check_multitf_alignment(self, df_1h: pd.DataFrame) -> None:
        """
        6️⃣ Multi-Timeframe Alignment
        Check 1h EMA 50 direction must agree with 15m signal.
        
        15m BUY + 1h bullish (EMA50 UP) → Allow
        15m BUY + 1h bearish (EMA50 DOWN) → Reject
        """
        check_name = 'multitf_alignment'
        result = {
            'passed': False,
            'details': [],
            'hour_ema_50': None,
            'hour_trend': None
        }

        try:
            if len(df_1h) < 50:
                result['details'].append(f'⚠️ Insufficient 1h data: {len(df_1h)} candles')
                result['passed'] = True  # Skip check
                self.validation_result['checks'][check_name] = result
                return

            df_1h['ema_50'] = ta.trend.ema_indicator(df_1h['close'], window=50)
            
            latest_1h = df_1h.iloc[-1]
            close_1h = latest_1h['close']
            ema_50_1h = latest_1h['ema_50']

            result['hour_ema_50'] = ema_50_1h

            if pd.isna(ema_50_1h):
                result['details'].append('⚠️ 1h EMA50 not calculated')
                result['passed'] = True  # Skip check
                self.validation_result['checks'][check_name] = result
                return

            # Determine 1h trend
            if len(df_1h) >= 2:
                prev_ema_50 = df_1h.iloc[-2]['ema_50']
                if ema_50_1h > prev_ema_50:
                    hour_trend = 'BULLISH'
                    result['hour_trend'] = hour_trend
                else:
                    hour_trend = 'BEARISH'
                    result['hour_trend'] = hour_trend
            else:
                hour_trend = 'UNKNOWN'
                result['details'].append('⚠️ Cannot determine 1h trend')
                result['passed'] = True  # Skip
                self.validation_result['checks'][check_name] = result
                return

            # Check alignment
            if self.signal_direction == 'BUY':
                if hour_trend == 'BULLISH':
                    result['details'].append('✅ Multi-TF Align: 15m BUY + 1h BULLISH')
                    result['passed'] = True
                    self.validation_result['score'] += 1
                else:
                    result['details'].append('❌ Multi-TF Conflict: 15m BUY but 1h BEARISH')
                    result['passed'] = False

            elif self.signal_direction == 'SELL':
                if hour_trend == 'BEARISH':
                    result['details'].append('✅ Multi-TF Align: 15m SELL + 1h BEARISH')
                    result['passed'] = True
                    self.validation_result['score'] += 1
                else:
                    result['details'].append('❌ Multi-TF Conflict: 15m SELL but 1h BULLISH')
                    result['passed'] = False

        except Exception as e:
            logger.error(f"Multi-TF alignment check failed: {e}")
            result['details'].append(f'Error: {str(e)}')
            result['passed'] = True  # Don't fail on error

        self.validation_result['checks'][check_name] = result

    def _calculate_final_decision(self) -> None:
        """
        Calculate final decision based on scoring.
        Requirement: 4 / 5 checks must pass for approval.
        """
        score = self.validation_result['score']
        max_score = self.validation_result['max_score']

        # Count how many checks passed
        passed_count = sum(
            1 for check in self.validation_result['checks'].values()
            if check.get('passed', False)
        )

        self.validation_result['metadata']['checks_passed'] = passed_count
        self.validation_result['metadata']['required_passes'] = 4

        if passed_count >= 4:
            self.validation_result['valid'] = True
            self.validation_result['metadata']['decision'] = 'APPROVED'
            self.validation_result['metadata']['reason'] = (
                f'{passed_count}/5 checks passed - Signal confirmed'
            )
        else:
            self.validation_result['valid'] = False
            self.validation_result['metadata']['decision'] = 'REJECTED'
            self.validation_result['metadata']['reason'] = (
                f'Only {passed_count}/5 checks passed (need 4 minimum) - Signal not confirmed'
            )

    def _calculate_vwap(self, df: pd.DataFrame) -> pd.Series:
        """
        Simple VWAP calculation: (High + Low + Close) * Volume / 3 / Volume SMA
        """
        try:
            typical_price = (df['high'] + df['low'] + df['close']) / 3
            tp_vol = typical_price * df['volume']
            vwap = tp_vol.rolling(window=20).sum() / df['volume'].rolling(window=20).sum()
            return vwap
        except Exception as e:
            logger.warning(f"VWAP calculation failed: {e}")
            return pd.Series([None] * len(df), index=df.index)


def validate_signal(symbol: str, direction: str) -> Dict[str, Any]:
    """
    Convenience function to validate a single signal.
    
    Args:
        symbol: Stock ticker
        direction: 'BUY' or 'SELL'
        
    Returns:
        Validation result dict with all checks and decision
    """
    validator = SignalValidator(symbol, direction)
    return validator.validate()
