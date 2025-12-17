import sqlite3
import os

db_path = 'trades.db'

if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if columns exist
        cursor.execute("PRAGMA table_info(trades)")
        columns = [col[1] for col in cursor.fetchall()]
        
        if 'validation_data' not in columns:
            cursor.execute("ALTER TABLE trades ADD COLUMN validation_data TEXT")
            conn.commit()
            print(f"✓ Added validation_data column to trades table")
        else:
            print(f"✓ Column validation_data already exists")
        
        if 'executed_price' not in columns:
            cursor.execute("ALTER TABLE trades ADD COLUMN executed_price REAL")
            conn.commit()
            print(f"✓ Added executed_price column to trades table")
        else:
            print(f"✓ Column executed_price already exists")
        
        conn.close()
    except Exception as e:
        print(f"Error migrating trades table: {e}")
else:
    print("Database file not found - will be created on startup")

# Migrate trade_settings table
print("\nMigrating trade_settings table...")
if os.path.exists(db_path):
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        
        # Check if trade_settings table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='trade_settings'")
        if cursor.fetchone():
            cursor.execute("PRAGMA table_info(trade_settings)")
            columns = [col[1] for col in cursor.fetchall()]
            
            if 'enable_signal_validation' not in columns:
                cursor.execute("ALTER TABLE trade_settings ADD COLUMN enable_signal_validation BOOLEAN DEFAULT 1")
                conn.commit()
                print(f"✓ Added enable_signal_validation column to trade_settings table")
            else:
                print(f"✓ Column enable_signal_validation already exists")
        else:
            print("✓ trade_settings table will be created on first run")
        
        conn.close()
    except Exception as e:
        print(f"Error migrating trade_settings table: {e}")
