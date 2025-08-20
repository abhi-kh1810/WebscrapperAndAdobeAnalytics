#!/usr/bin/env python3
"""
Database Management Utilities for Modern Scraper

Utility functions to manage the SQLite database:
- Clear all data
- Remove duplicates
- View database stats
- Export/import data

Usage: python db_utils.py [command]
Commands: clear, stats, duplicates, export, import
"""

import sqlite3
import json
import sys
from pathlib import Path
from datetime import datetime

DATABASE_FILE = "scraper_data.db"


def clear_database():
    """Clear all data from the database."""
    if not Path(DATABASE_FILE).exists():
        print("Database file not found.")
        return
    
    response = input("Are you sure you want to clear ALL data? (yes/no): ")
    if response.lower() != 'yes':
        print("Operation cancelled.")
        return
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Clear all tables
    cursor.execute('DELETE FROM subscription_results')
    cursor.execute('DELETE FROM subscriptions')
    cursor.execute('DELETE FROM scraping_sessions')
    
    # Reset auto-increment counters
    cursor.execute('DELETE FROM sqlite_sequence WHERE name IN ("subscriptions", "subscription_results", "scraping_sessions")')
    
    conn.commit()
    conn.close()
    
    print("Database cleared successfully!")


def show_stats():
    """Show database statistics."""
    if not Path(DATABASE_FILE).exists():
        print("Database file not found.")
        return
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Get counts
    cursor.execute('SELECT COUNT(*) FROM subscriptions')
    total_subscriptions = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM subscription_results')
    total_results = cursor.fetchone()[0]
    
    cursor.execute('SELECT COUNT(*) FROM scraping_sessions')
    total_sessions = cursor.fetchone()[0]
    
    # Get latest data
    cursor.execute('SELECT MAX(last_scraped) FROM subscriptions')
    last_scrape = cursor.fetchone()[0]
    
    # Get subscription details
    cursor.execute('''
        SELECT subscription_search, total_results, last_scraped, status 
        FROM subscriptions 
        ORDER BY last_scraped DESC
    ''')
    subscriptions = cursor.fetchall()
    
    conn.close()
    
    print("Database Statistics")
    print("=" * 40)
    print(f"Total Subscriptions: {total_subscriptions}")
    print(f"Total Results: {total_results}")
    print(f"Total Sessions: {total_sessions}")
    print(f"Last Scrape: {last_scrape}")
    print()
    
    if subscriptions:
        print("Subscription Details:")
        print("-" * 80)
        print(f"{'Search Term':<40} {'Results':<10} {'Last Scraped':<20} {'Status'}")
        print("-" * 80)
        for sub in subscriptions:
            print(f"{sub[0]:<40} {sub[1]:<10} {sub[2]:<20} {sub[3]}")


def remove_duplicates():
    """Remove duplicate subscription results."""
    if not Path(DATABASE_FILE).exists():
        print("Database file not found.")
        return
    
    conn = sqlite3.connect(DATABASE_FILE)
    cursor = conn.cursor()
    
    # Find duplicates based on subscription_search
    cursor.execute('''
        SELECT subscription_search, COUNT(*) as count
        FROM subscriptions
        GROUP BY subscription_search
        HAVING COUNT(*) > 1
    ''')
    
    duplicates = cursor.fetchall()
    
    if not duplicates:
        print("No duplicates found.")
        conn.close()
        return
    
    print(f"Found {len(duplicates)} duplicate subscription groups:")
    for dup in duplicates:
        print(f"  - {dup[0]}: {dup[1]} entries")
    
    response = input("Remove duplicates? (yes/no): ")
    if response.lower() != 'yes':
        print("Operation cancelled.")
        conn.close()
        return
    
    # Remove duplicates, keeping the most recent
    for search_term, count in duplicates:
        cursor.execute('''
            DELETE FROM subscriptions 
            WHERE subscription_search = ? 
            AND id NOT IN (
                SELECT id FROM subscriptions 
                WHERE subscription_search = ? 
                ORDER BY last_scraped DESC 
                LIMIT 1
            )
        ''', (search_term, search_term))
    
    # Remove orphaned results
    cursor.execute('''
        DELETE FROM subscription_results 
        WHERE subscription_id NOT IN (SELECT id FROM subscriptions)
    ''')
    
    rows_affected = cursor.rowcount
    conn.commit()
    conn.close()
    
    print(f"Removed duplicates. {rows_affected} rows affected.")


def export_data(filename: str = None):
    """Export database to JSON file."""
    if not Path(DATABASE_FILE).exists():
        print("Database file not found.")
        return
    
    if not filename:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"database_export_{timestamp}.json"
    
    conn = sqlite3.connect(DATABASE_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    # Export all data
    data = {
        "export_timestamp": datetime.now().isoformat(),
        "subscriptions": [],
        "sessions": []
    }
    
    # Get subscriptions with results
    cursor.execute('''
        SELECT s.*, 
               json_group_array(
                   json_object(
                       'result_id', r.result_id,
                       'sitename', r.sitename,
                       'edison_lite_id', r.edison_lite_id,
                       'state', r.state,
                       'assigned_team', r.assigned_team,
                       'webcomponent_version', r.webcomponent_version,
                       'is_live', r.is_live,
                       'updated_at', r.updated_at,
                       'scraped_timestamp', r.scraped_timestamp
                   )
               ) as results
        FROM subscriptions s
        LEFT JOIN subscription_results r ON s.id = r.subscription_id
        GROUP BY s.id
    ''')
    
    for row in cursor.fetchall():
        subscription_data = dict(row)
        subscription_data['results'] = json.loads(subscription_data['results']) if subscription_data['results'] else []
        data['subscriptions'].append(subscription_data)
    
    # Get sessions
    cursor.execute('SELECT * FROM scraping_sessions ORDER BY started_at DESC')
    data['sessions'] = [dict(row) for row in cursor.fetchall()]
    
    conn.close()
    
    # Save to file
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    print(f"Data exported to: {filename}")


def main():
    """Main CLI interface."""
    if len(sys.argv) < 2:
        print("Usage: python db_utils.py [command]")
        print("Commands:")
        print("  clear      - Clear all database data")
        print("  stats      - Show database statistics")
        print("  duplicates - Remove duplicate subscriptions")
        print("  export     - Export database to JSON")
        return
    
    command = sys.argv[1].lower()
    
    if command == "clear":
        clear_database()
    elif command == "stats":
        show_stats()
    elif command == "duplicates":
        remove_duplicates()
    elif command == "export":
        filename = sys.argv[2] if len(sys.argv) > 2 else None
        export_data(filename)
    else:
        print(f"Unknown command: {command}")
        print("Available commands: clear, stats, duplicates, export")


if __name__ == "__main__":
    main()
