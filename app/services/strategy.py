def validate_signal(signal):
    if signal.qty <= 0:
        return False
    if signal.side.upper() not in ["BUY", "SELL"]:
        return False
    return True