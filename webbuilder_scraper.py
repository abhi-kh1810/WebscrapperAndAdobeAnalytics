#!/usr/bin/env python3
"""
Modern Data Viewer - Web interface for scraped data

Features:
- Real-time data viewing
- Search and filtering
- JSON API endpoints
- Export capabilities
- Statistics dashboard

Run: python data_viewer.py
Then open: http://localhost:8080
"""

import json
import sqlite3
import asyncio
import logging
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Dict, List, Any
import threading
import time

# Indian Standard Time (IST) is UTC+5:30
IST = timezone(timedelta(hours=5, minutes=30))

def get_ist_now():
    """Get current datetime in Indian Standard Time."""
    return datetime.now(IST)

def get_ist_timestamp():
    """Get current IST timestamp as ISO format string."""
    return get_ist_now().isoformat()

def format_ist_timestamp(timestamp_str):
    """Format a timestamp string to display IST timezone."""
    if not timestamp_str:
        return timestamp_str
    try:
        # If it's already an IST timestamp, return as is
        if '+05:30' in timestamp_str or '+0530' in timestamp_str:
            return timestamp_str
        # If it's a naive timestamp, assume it's UTC and convert to IST
        dt = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        ist_dt = dt.astimezone(IST)
        return ist_dt.isoformat()
    except:
        return timestamp_str

try:
    from flask import Flask, render_template_string, jsonify, request, send_file
except ImportError:
    print("Flask not installed. Install with: pip install flask")
    exit(1)

try:
    from playwright.async_api import async_playwright, Page, Browser, BrowserContext
    from playwright.async_api import TimeoutError as PlaywrightTimeoutError
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("Playwright not available. Scraping functionality will be disabled.")

app = Flask(__name__)

DATABASE_FILE = "scraper_data.db"
SUBSCRIPTION_FILE = "subscription.txt"
DASHBOARD_URL = "https://webbuilder.pfizer/webbuilder/dashboard/"

# Login configuration
LOGIN_SELECTORS = {
    "username_input": 'input[name="username"], input[type="email"], input[id*="username"], input[id*="email"], input[placeholder*="username"], input[placeholder*="email"]',
    "password_input": 'input[name="password"], input[type="password"], input[id*="password"], input[placeholder*="password"]',
    "login_button": 'button[type="submit"], input[type="submit"], button:has-text("Login"), button:has-text("Sign in"), button:has-text("Log in")',
    "login_form": 'form',
    "sso_button": 'button:has-text("SSO"), button:has-text("Single Sign"), a:has-text("SSO")'
}

# Optimized scraping configuration for speed
SELECTORS = {
    "search_input": 'input[type="text"], input[placeholder*="search"], input[name*="search"], input[class*="search"]',
    "results_table": 'table, .table, [role="table"]',
    "table_rows": 'tr',
    "table_cells": 'td',
    "no_results": '.no-results, .empty-state, :has-text("No results found")',
    "loading": '.loading, .spinner, [data-loading="true"]'
}

# Optimized timing for faster scraping
SEARCH_WAIT_TIME = 1  # Reduced from 2 to 1 second
PAGE_LOAD_TIMEOUT = 15000  # Reduced from 30000 to 15000ms
ELEMENT_TIMEOUT = 5000  # Reduced from 10000 to 5000ms
BETWEEN_SEARCHES_WAIT = 0.5  # Reduced wait between searches

# Global scraping status
scraping_status = {
    "is_running": False,
    "progress": 0,
    "total": 0,
    "current_subscription": "",
    "message": "Ready",
    "last_update": get_ist_timestamp()
}

HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>🔥 Modern Scraper Data Viewer</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { 
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            min-height: 100vh;
            color: #333;
        }
        .container { max-width: 1400px; margin: 0 auto; padding: 20px; }
        .header {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 20px;
            padding: 30px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .header h1 { 
            font-size: 2.5rem; 
            background: linear-gradient(45deg, #667eea, #764ba2);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 10px;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }
        .stat-card {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            transition: transform 0.3s ease;
        }
        .stat-card:hover { transform: translateY(-5px); }
        .stat-number { 
            font-size: 2.5rem; 
            font-weight: bold; 
            color: #667eea;
            display: block;
        }
        .stat-label { 
            color: #666; 
            margin-top: 5px;
            font-size: 0.9rem;
        }
        .controls {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .controls input, .controls select, .controls button {
            padding: 12px 20px;
            border: 2px solid #e1e5e9;
            border-radius: 10px;
            margin: 5px;
            font-size: 14px;
            transition: all 0.3s ease;
        }
        .controls input:focus, .controls select:focus {
            outline: none;
            border-color: #667eea;
            box-shadow: 0 0 0 3px rgba(102, 126, 234, 0.1);
        }
        .controls button {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            border: none;
            cursor: pointer;
            font-weight: 600;
        }
        .controls button:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .data-table {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            overflow: hidden;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        table {
            width: 100%;
            border-collapse: collapse;
        }
        th {
            background: linear-gradient(45deg, #667eea, #764ba2);
            color: white;
            padding: 20px 15px;
            text-align: left;
            font-weight: 600;
        }
        td {
            padding: 15px;
            border-bottom: 1px solid #f0f0f0;
            vertical-align: top;
        }
        tr:hover { background: rgba(102, 126, 234, 0.05); }
        .status-live { 
            background: #10b981; 
            color: white; 
            padding: 4px 8px; 
            border-radius: 20px; 
            font-size: 12px;
        }
        .status-no { 
            background: #ef4444; 
            color: white; 
            padding: 4px 8px; 
            border-radius: 20px; 
            font-size: 12px;
        }
        .loading {
            text-align: center;
            padding: 50px;
            font-size: 1.2rem;
            color: #667eea;
        }
        .export-buttons {
            margin: 20px 0;
        }
        .export-buttons a {
            display: inline-block;
            padding: 12px 25px;
            background: #10b981;
            color: white;
            text-decoration: none;
            border-radius: 10px;
            margin-right: 10px;
            font-weight: 600;
            transition: all 0.3s ease;
        }
        .export-buttons a:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 15px rgba(0,0,0,0.2);
        }
        .scraping-status {
            background: rgba(255,255,255,0.95);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 25px;
            margin-bottom: 30px;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
        }
        .status-header {
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 15px;
        }
        .status-header h3 {
            margin: 0;
            color: #667eea;
        }
        .progress-bar {
            background: #f0f0f0;
            border-radius: 10px;
            height: 20px;
            position: relative;
            overflow: hidden;
            margin-bottom: 10px;
        }
        .progress-fill {
            background: linear-gradient(45deg, #667eea, #764ba2);
            height: 100%;
            transition: width 0.3s ease;
            border-radius: 10px;
        }
        .progress-text {
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 12px;
            font-weight: bold;
            color: #333;
        }
        .current-subscription {
            font-size: 14px;
            color: #666;
            font-style: italic;
        }
        #scrapeButton:disabled {
            background: #ccc !important;
            cursor: not-allowed !important;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>🔥 Modern Scraper Data Viewer</h1>
            <p>Real-time dashboard for Pfizer Webbuilder subscription data</p>
        </div>

        <div class="stats-grid" id="statsGrid">
            <div class="stat-card">
                <span class="stat-number" id="totalSubscriptions">-</span>
                <span class="stat-label">Total Subscriptions</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="totalResults">-</span>
                <span class="stat-label">Total Results</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="totalSessions">-</span>
                <span class="stat-label">Scraping Sessions</span>
            </div>
            <div class="stat-card">
                <span class="stat-number" id="lastUpdate">-</span>
                <span class="stat-label">Last Update</span>
            </div>
        </div>

        <div class="controls">
            <input type="text" id="searchInput" placeholder="🔍 Search subscriptions, sites, teams..." />
            <select id="stateFilter">
                <option value="">All States</option>
                <option value="Editor">Editor</option>
                <option value="Production">Production</option>
                <option value="Approved">Approved</option>
                <option value="Pre-Production">Pre-Production</option>
            </select>
            <select id="liveFilter">
                <option value="">All Status</option>
                <option value="Yes">Live</option>
                <option value="No">Not Live</option>
            </select>
            <button onclick="startScrapingManual()" id="scrapeManualButton">👤 Scrape with Manual Login</button>
        </div>

        <div class="scraping-status" id="scrapingStatus" style="display: none;">
            <div class="status-header">
                <h3>🕷️ Scraping Progress</h3>
                <span id="scrapingMessage">Ready</span>
            </div>
            <div class="progress-bar">
                <div class="progress-fill" id="progressFill"></div>
                <span class="progress-text" id="progressText">0 / 0</span>
            </div>
            <div class="current-subscription" id="currentSubscription"></div>
        </div>

        <div class="export-buttons">
            <a href="/api/export/json" target="_blank">📄 Download JSON</a>
            <a href="/api/export/csv" target="_blank">📊 Download CSV</a>
            <a href="/api/stats" target="_blank">📈 API Stats</a>
            <a href="/api/scraping/subscriptions" target="_blank">📋 View Subscriptions</a>
        </div>

        <div class="data-table">
            <div id="loadingMessage" class="loading">Loading data...</div>
            <table id="dataTable" style="display: none;">
                <thead>
                    <tr>
                        <th>Subscription</th>
                        <th>Site ID</th>
                        <th>Sitename</th>
                        <th>Edison Lite ID</th>
                        <th>State</th>
                        <th>Team</th>
                        <th>Version</th>
                        <th>Live?</th>
                        <th>Updated</th>
                    </tr>
                </thead>
                <tbody id="dataTableBody">
                </tbody>
            </table>
        </div>
    </div>

    <script>
        let allData = [];

        async function loadStats() {
            try {
                const response = await fetch('/api/stats');
                const stats = await response.json();
                
                document.getElementById('totalSubscriptions').textContent = stats.total_subscriptions;
                document.getElementById('totalResults').textContent = stats.total_results;
                document.getElementById('totalSessions').textContent = stats.total_sessions;
                document.getElementById('lastUpdate').textContent = stats.last_scrape ? 
                    new Date(stats.last_scrape).toLocaleDateString() : 'Never';
            } catch (error) {
                console.error('Error loading stats:', error);
            }
        }

        async function loadData() {
            try {
                document.getElementById('loadingMessage').style.display = 'block';
                document.getElementById('dataTable').style.display = 'none';
                
                const response = await fetch('/api/data');
                const data = await response.json();
                allData = data;
                
                renderTable(allData);
                
                document.getElementById('loadingMessage').style.display = 'none';
                document.getElementById('dataTable').style.display = 'table';
            } catch (error) {
                console.error('Error loading data:', error);
                document.getElementById('loadingMessage').textContent = 'Error loading data';
            }
        }

        function renderTable(data) {
            const tbody = document.getElementById('dataTableBody');
            tbody.innerHTML = '';

            data.forEach(item => {
                item.results.forEach(result => {
                    const row = document.createElement('tr');
                    
                    const liveStatus = result.is_live === 'Yes' ? 
                        '<span class="status-live">Live</span>' : 
                        '<span class="status-no">Not Live</span>';
                    
                    row.innerHTML = `
                        <td><strong>${item.search_term}</strong></td>
                        <td><code>${result.result_id}</code></td>
                        <td>${result.sitename}</td>
                        <td>${result.edison_lite_id}</td>
                        <td>${result.state}</td>
                        <td>${result.assigned_team}</td>
                        <td><small>${result.webcomponent_version}</small></td>
                        <td>${liveStatus}</td>
                        <td><small>${result.updated_at}</small></td>
                    `;
                    
                    tbody.appendChild(row);
                });
            });
        }

        function filterData() {
            const searchTerm = document.getElementById('searchInput').value.toLowerCase();
            const stateFilter = document.getElementById('stateFilter').value;
            const liveFilter = document.getElementById('liveFilter').value;

            const filtered = allData.map(item => {
                const filteredResults = item.results.filter(result => {
                    const matchesSearch = !searchTerm || 
                        item.search_term.toLowerCase().includes(searchTerm) ||
                        result.sitename.toLowerCase().includes(searchTerm) ||
                        result.assigned_team.toLowerCase().includes(searchTerm) ||
                        result.edison_lite_id.toLowerCase().includes(searchTerm);
                    
                    const matchesState = !stateFilter || result.state === stateFilter;
                    const matchesLive = !liveFilter || result.is_live === liveFilter;
                    
                    return matchesSearch && matchesState && matchesLive;
                });

                return { ...item, results: filteredResults };
            }).filter(item => item.results.length > 0);

            renderTable(filtered);
        }

        function refreshData() {
            loadStats();
            loadData();
        }

        function exportData() {
            window.open('/api/export/json', '_blank');
        }

        async function startScraping() {
            await startScrapingWithMode(true); // headless mode
        }

        async function startScrapingManual() {
            await startScrapingWithMode(false); // visible mode for manual login
        }

        async function startScrapingWithMode(headless) {
            try {
                const button = document.getElementById('scrapeButton');
                const manualButton = document.getElementById('scrapeManualButton');
                
                // Only disable buttons that exist
                if (button) {
                    button.disabled = true;
                }
                if (manualButton) {
                    manualButton.disabled = true;
                }
                
                const buttonText = headless ? '🕷️ Starting...' : '👤 Starting (Manual Login)...';
                
                // Only update text for the button that exists
                if (headless && button) {
                    button.textContent = buttonText;
                } else if (!headless && manualButton) {
                    manualButton.textContent = buttonText;
                }
                
                // Show scraping status
                document.getElementById('scrapingStatus').style.display = 'block';
                
                const endpoint = headless ? '/api/scraping/start' : '/api/scraping/start-manual';
                const response = await fetch(endpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json'
                    },
                    body: JSON.stringify({ headless: headless })
                });
                const result = await response.json();
                
                if (result.success) {
                    // Start monitoring progress
                    monitorScrapingProgress();
                    
                    if (!headless) {
                        alert('Browser opened for manual login. Please login to Pfizer webbuilder, then scraping will start automatically.');
                    }
                } else {
                    alert('Failed to start scraping: ' + result.message);
                    if (button) {
                        button.disabled = false;
                        button.textContent = '🕷️ Scrape New Data';
                    }
                    if (manualButton) {
                        manualButton.disabled = false;
                        manualButton.textContent = '� Scrape with Manual Login';
                    }
                    document.getElementById('scrapingStatus').style.display = 'none';
                }
            } catch (error) {
                console.error('Error starting scraping:', error);
                alert('Error starting scraping: ' + error.message);
                const button = document.getElementById('scrapeButton');
                const manualButton = document.getElementById('scrapeManualButton');
                if (button) {
                    button.disabled = false;
                    button.textContent = '🕷️ Scrape New Data';
                }
                if (manualButton) {
                    manualButton.disabled = false;
                    manualButton.textContent = '� Scrape with Manual Login';
                }
            }
        }

        async function monitorScrapingProgress() {
            const statusInterval = setInterval(async () => {
                try {
                    const response = await fetch('/api/scraping/status');
                    const status = await response.json();
                    
                    updateScrapingUI(status);
                    
                    if (!status.is_running) {
                        clearInterval(statusInterval);
                        const button = document.getElementById('scrapeButton');
                        const fastButton = document.getElementById('scrapeFastButton');
                        const manualButton = document.getElementById('scrapeManualButton');
                        
                        if (button) {
                            button.disabled = false;
                            button.textContent = '🕷️ Scrape New Data';
                        }
                        if (fastButton) {
                            fastButton.disabled = false;
                            fastButton.textContent = '⚡ Fast Parallel Scrape';
                        }
                        if (manualButton) {
                            manualButton.disabled = false;
                            manualButton.textContent = '👤 Scrape with Manual Login';
                        }
                        
                        // Refresh data after scraping completes
                        setTimeout(() => {
                            refreshData();
                            document.getElementById('scrapingStatus').style.display = 'none';
                        }, 3000);
                    }
                } catch (error) {
                    console.error('Error monitoring scraping:', error);
                    clearInterval(statusInterval);
                }
            }, 1000);
        }

        function updateScrapingUI(status) {
            document.getElementById('scrapingMessage').textContent = status.message;
            document.getElementById('progressText').textContent = `${status.progress} / ${status.total}`;
            document.getElementById('currentSubscription').textContent = 
                status.current_subscription ? `Currently processing: ${status.current_subscription}` : '';
            
            const progressPercent = status.total > 0 ? (status.progress / status.total) * 100 : 0;
            document.getElementById('progressFill').style.width = progressPercent + '%';
        }

        // Event listeners
        document.getElementById('searchInput').addEventListener('input', filterData);
        document.getElementById('stateFilter').addEventListener('change', filterData);
        document.getElementById('liveFilter').addEventListener('change', filterData);

        // Initial load
        refreshData();
        
        // Auto-refresh every 30 seconds
        setInterval(refreshData, 30000);
    </script>
</body>
</html>
"""


class DataViewer:
    """Modern data viewer with web interface and integrated scraping."""
    
    def __init__(self, db_path: str = DATABASE_FILE):
        self.db_path = db_path
        self.init_database()
        
        # Setup logging
        logging.basicConfig(
            level=logging.INFO,
            format='%(asctime)s - %(levelname)s - %(message)s',
            handlers=[
                logging.FileHandler('data_viewer.log'),
                logging.StreamHandler()
            ]
        )
        self.logger = logging.getLogger(__name__)
    
    def init_database(self):
        """Initialize SQLite database with modern schema."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Main subscriptions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscriptions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_search TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_scraped TIMESTAMP,
                total_results INTEGER DEFAULT 0,
                status TEXT DEFAULT 'pending'
            )
        ''')
        
        # Detailed results table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS subscription_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subscription_id INTEGER,
                session_id INTEGER,
                result_id TEXT NOT NULL,
                sitename TEXT,
                edison_lite_id TEXT,
                state TEXT,
                assigned_team TEXT,
                webcomponent_version TEXT,
                is_live TEXT,
                updated_at TEXT,
                scraped_timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (subscription_id) REFERENCES subscriptions (id),
                FOREIGN KEY (session_id) REFERENCES scraping_sessions (id)
            )
        ''')
        
        # Scraping sessions for tracking
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scraping_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                ended_at TIMESTAMP,
                total_subscriptions INTEGER,
                successful_scrapes INTEGER,
                failed_scrapes INTEGER,
                session_notes TEXT
            )
        ''')
        
        # Add session_id column to existing tables if not exists
        try:
            cursor.execute('ALTER TABLE subscription_results ADD COLUMN session_id INTEGER')
        except sqlite3.OperationalError:
            # Column already exists
            pass
        
        try:
            cursor.execute('ALTER TABLE subscriptions ADD COLUMN session_id INTEGER')
        except sqlite3.OperationalError:
            # Column already exists  
            pass
        
        conn.commit()
        conn.close()
    
    def get_stats(self) -> Dict[str, Any]:
        """Get summary statistics."""
        if not Path(self.db_path).exists():
            return {
                "total_subscriptions": 0,
                "total_results": 0,
                "total_sessions": 0,
                "last_scrape": None
            }
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('SELECT COUNT(*) FROM subscriptions')
        total_subscriptions = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM subscription_results')
        total_results = cursor.fetchone()[0]
        
        cursor.execute('SELECT COUNT(*) FROM scraping_sessions')
        total_sessions = cursor.fetchone()[0]
        
        cursor.execute('SELECT MAX(scraped_timestamp) FROM subscription_results')
        last_scrape = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            "total_subscriptions": total_subscriptions,
            "total_results": total_results,
            "total_sessions": total_sessions,
            "last_scrape": last_scrape
        }
    
    def clear_all_data(self):
        """Clear all subscription and result data for a fresh start."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Clear all data from tables
        cursor.execute('DELETE FROM subscription_results')
        cursor.execute('DELETE FROM subscriptions')
        cursor.execute('DELETE FROM scraping_sessions')
        
        # Reset the auto-increment counters
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='subscription_results'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='subscriptions'")
        cursor.execute("DELETE FROM sqlite_sequence WHERE name='scraping_sessions'")
        
        conn.commit()
        conn.close()
        
        self.logger.info("Cleared all existing data for fresh scraping session")
    
    def create_scraping_session(self, total_subscriptions: int) -> int:
        """Create a new scraping session and return its ID."""
        # Clear all existing data first
        self.clear_all_data()
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            INSERT INTO scraping_sessions (total_subscriptions, successful_scrapes, failed_scrapes)
            VALUES (?, 0, 0)
        ''', (total_subscriptions,))
        
        session_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        self.logger.info(f"Created new scraping session {session_id} after clearing all data")
        return session_id
    
    def update_scraping_session(self, session_id: int, successful_scrapes: int, failed_scrapes: int, notes: str = None):
        """Update a scraping session with final results."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        cursor.execute('''
            UPDATE scraping_sessions 
            SET ended_at = ?, successful_scrapes = ?, failed_scrapes = ?, session_notes = ?
            WHERE id = ?
        ''', (get_ist_timestamp(), successful_scrapes, failed_scrapes, notes, session_id))
        
        conn.commit()
        conn.close()
    
    def get_latest_session_stats(self) -> Dict[str, Any]:
        """Get statistics for the latest scraping session."""
        if not Path(self.db_path).exists():
            return {
                "total_subscriptions": 0,
                "total_results": 0,
                "total_sessions": 0,
                "last_scrape": None,
                "latest_session": None
            }
        
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        # Get latest session info
        cursor.execute('''
            SELECT id, started_at, ended_at, total_subscriptions, successful_scrapes, failed_scrapes, session_notes
            FROM scraping_sessions 
            ORDER BY started_at DESC 
            LIMIT 1
        ''')
        latest_session = cursor.fetchone()
        
        if latest_session:
            session_id = latest_session[0]
            
            # Count all current subscriptions (since we clear data each session)
            cursor.execute('SELECT COUNT(*) FROM subscriptions')
            session_subscriptions = cursor.fetchone()[0]
            
            # Count all current results (since we clear data each session)
            cursor.execute('SELECT COUNT(*) FROM subscription_results')
            session_results = cursor.fetchone()[0]
            
            cursor.execute('SELECT COUNT(*) FROM scraping_sessions')
            total_sessions = cursor.fetchone()[0]
            
            cursor.execute('SELECT MAX(scraped_timestamp) FROM subscription_results')
            last_scrape = cursor.fetchone()[0]
            
            conn.close()
            
            return {
                "total_subscriptions": session_subscriptions,  # Show current session counts
                "total_results": session_results,             # Show current session counts  
                "total_sessions": total_sessions,
                "last_scrape": last_scrape,
                "latest_session": {
                    "id": session_id,
                    "started_at": latest_session[1],
                    "ended_at": latest_session[2],
                    "planned_subscriptions": latest_session[3],
                    "successful_scrapes": latest_session[4],
                    "failed_scrapes": latest_session[5],
                    "notes": latest_session[6]
                },
                "all_time": {
                    "total_subscriptions": session_subscriptions,  # Same as current since we clear each time
                    "total_results": session_results
                }
            }
        else:
            # No sessions yet, return zeros
            conn.close()
            return {
                "total_subscriptions": 0,
                "total_results": 0,
                "total_sessions": 0,
                "last_scrape": None,
                "latest_session": None
            }
    
    def get_all_data(self) -> List[Dict[str, Any]]:
        """Get all subscription data from current session."""
        if not Path(self.db_path).exists():
            return []
        
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        
        # Since we clear data each session, just get all current data
        cursor.execute('''
            SELECT 
                s.subscription_search,
                s.created_at,
                s.last_scraped,
                s.total_results,
                s.status,
                r.result_id,
                r.sitename,
                r.edison_lite_id,
                r.state,
                r.assigned_team,
                r.webcomponent_version,
                r.is_live,
                r.updated_at,
                r.scraped_timestamp
            FROM subscriptions s
            LEFT JOIN subscription_results r ON s.id = r.subscription_id
            ORDER BY s.last_scraped DESC, r.result_id
        ''')
        
        # Group results by subscription
        subscriptions = {}
        for row in cursor.fetchall():
            search_term = row["subscription_search"]
            
            if search_term not in subscriptions:
                subscriptions[search_term] = {
                    "search_term": search_term,
                    "created_at": row["created_at"],
                    "last_scraped": row["last_scraped"],
                    "total_results": row["total_results"],
                    "status": row["status"],
                    "results": []
                }
            
            if row["result_id"]:  # Only add if there's actual result data
                subscriptions[search_term]["results"].append({
                    "result_id": row["result_id"],
                    "sitename": row["sitename"],
                    "edison_lite_id": row["edison_lite_id"],
                    "state": row["state"],
                    "assigned_team": row["assigned_team"],
                    "webcomponent_version": row["webcomponent_version"],
                    "is_live": row["is_live"],
                    "updated_at": row["updated_at"],
                    "scraped_timestamp": row["scraped_timestamp"]
                })
        
        conn.close()
        return list(subscriptions.values())
    
    def export_to_json(self) -> Dict[str, Any]:
        """Export data to JSON format."""
        data = {
            "export_timestamp": get_ist_timestamp(),
            "stats": self.get_stats(),
            "subscriptions": self.get_all_data()
        }
        return data
    
    def export_to_csv(self) -> str:
        """Export data to CSV format."""
        import io
        import csv
        
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write header
        writer.writerow([
            "Search Term", "Site ID", "Sitename", "Edison Lite ID", 
            "State", "Assigned Team", "Version", "Live?", "Updated At", "Scraped At"
        ])
        
        # Write data
        for subscription in self.get_all_data():
            for result in subscription["results"]:
                writer.writerow([
                    subscription["search_term"],
                    result["result_id"],
                    result["sitename"],
                    result["edison_lite_id"],
                    result["state"],
                    result["assigned_team"],
                    result["webcomponent_version"],
                    result["is_live"],
                    result["updated_at"],
                    result["scraped_timestamp"]
                ])
        
        return output.getvalue()
    
    def read_subscription_ids(self) -> List[str]:
        """Read subscription IDs from file."""
        try:
            if not Path(SUBSCRIPTION_FILE).exists():
                self.logger.error(f"Subscription file {SUBSCRIPTION_FILE} not found")
                return []
            
            with open(SUBSCRIPTION_FILE, 'r', encoding='utf-8') as f:
                subscription_ids = [line.strip() for line in f if line.strip()]
            
            self.logger.info(f"Read {len(subscription_ids)} subscription IDs")
            return subscription_ids
            
        except Exception as e:
            self.logger.error(f"Failed to read subscription file: {e}")
            return []
    
    def update_scraping_status(self, is_running: bool, progress: int = 0, total: int = 0, 
                              current_subscription: str = "", message: str = ""):
        """Update global scraping status."""
        global scraping_status
        scraping_status.update({
            "is_running": is_running,
            "progress": progress,
            "total": total,
            "current_subscription": current_subscription,
            "message": message,
            "last_update": get_ist_timestamp()
        })
    
    async def handle_login(self, page: Page) -> bool:
        """Handle login process for Pfizer webbuilder."""
        try:
            self.logger.info("Attempting to handle login process...")
            
            # Navigate to dashboard URL (will redirect to login if needed)
            await page.goto(DASHBOARD_URL, timeout=PAGE_LOAD_TIMEOUT)
            await page.wait_for_load_state('networkidle')
            
            current_url = page.url
            self.logger.info(f"Current URL after navigation: {current_url}")
            
            # Check if we're already on the dashboard (already logged in)
            if "dashboard" in current_url.lower() and "login" not in current_url.lower():
                self.logger.info("Already logged in or no login required")
                return True
            
            # Wait a bit for any redirects to complete
            await asyncio.sleep(2)
            current_url = page.url
            self.logger.info(f"URL after waiting: {current_url}")
            
            # Check for SSO or enterprise login
            try:
                sso_button = await page.wait_for_selector(LOGIN_SELECTORS["sso_button"], timeout=5000)
                if sso_button:
                    self.logger.info("Found SSO button, clicking...")
                    await sso_button.click()
                    await page.wait_for_load_state('networkidle')
                    
                    # Wait for potential redirect or authentication flow
                    await asyncio.sleep(5)
                    
                    # Check if we reached dashboard
                    current_url = page.url
                    if "dashboard" in current_url.lower():
                        self.logger.info("Successfully authenticated via SSO")
                        return True
            except PlaywrightTimeoutError:
                self.logger.info("No SSO button found, trying standard login")
            
            # Check for username/password login form
            try:
                username_input = await page.wait_for_selector(LOGIN_SELECTORS["username_input"], timeout=5000)
                password_input = await page.wait_for_selector(LOGIN_SELECTORS["password_input"], timeout=2000)
                
                if username_input and password_input:
                    self.logger.warning("Username/Password login form detected")
                    self.logger.warning("This requires manual authentication or stored credentials")
                    
                    # For security, we don't auto-fill credentials
                    # User would need to manually login in a non-headless browser
                    return False
                    
            except PlaywrightTimeoutError:
                pass
            
            # Check if we somehow made it to the dashboard
            await asyncio.sleep(3)
            current_url = page.url
            if "dashboard" in current_url.lower() and "login" not in current_url.lower():
                self.logger.info("Successfully reached dashboard")
                return True
            
            self.logger.error(f"Unable to authenticate. Current URL: {current_url}")
            return False
            
        except Exception as e:
            self.logger.error(f"Login handling failed: {e}")
            return False
    
    async def navigate_to_dashboard_with_auth(self, page: Page) -> bool:
        """Navigate to dashboard with authentication handling."""
        try:
            # First attempt to handle login
            login_success = await self.handle_login(page)
            
            if not login_success:
                self.logger.error("Authentication failed or requires manual intervention")
                return False
            
            # Verify we're on the dashboard
            current_url = page.url
            if "dashboard" not in current_url.lower():
                self.logger.info("Not on dashboard yet, navigating...")
                await page.goto(DASHBOARD_URL, timeout=PAGE_LOAD_TIMEOUT)
                await page.wait_for_load_state('networkidle')
            
            # Final verification
            current_url = page.url
            if "dashboard" in current_url.lower():
                self.logger.info("Successfully authenticated and on dashboard")
                return True
            else:
                self.logger.error(f"Failed to reach dashboard. Final URL: {current_url}")
                return False
                
        except Exception as e:
            self.logger.error(f"Dashboard navigation with auth failed: {e}")
            return False

    async def scrape_subscription_data(self, subscription_id: str, page: Page, is_first_search: bool = False) -> List[Dict[str, str]]:
        """Scrape data for a single subscription."""
        try:
            self.logger.info(f"Scraping subscription: {subscription_id}")
            
            # Only handle auth on first search to avoid repeated login attempts
            if is_first_search:
                auth_success = await self.navigate_to_dashboard_with_auth(page)
                if not auth_success:
                    self.logger.error("Authentication failed, cannot proceed with scraping")
                    return []
            else:
                # For subsequent searches, just navigate to dashboard
                current_url = page.url
                if "dashboard" not in current_url.lower():
                    await page.goto(DASHBOARD_URL, timeout=PAGE_LOAD_TIMEOUT)
                    await page.wait_for_load_state('networkidle')
            
            # Find and use search input
            search_input = None
            search_selectors = [
                'input[type="text"]',
                'input[placeholder*="search"]', 
                'input[name*="search"]',
                'input[class*="search"]',
                'input:first-of-type'
            ]
            
            for selector in search_selectors:
                try:
                    search_input = await page.wait_for_selector(selector, timeout=5000)
                    if search_input:
                        self.logger.info(f"Found search input with selector: {selector}")
                        break
                except PlaywrightTimeoutError:
                    continue
            
            if not search_input:
                self.logger.error("Could not find search input field")
                return []
            
            # Perform optimized search
            await search_input.click()
            await search_input.fill("")
            await search_input.type(subscription_id, delay=50)  # Reduced delay from 100 to 50ms
            await search_input.press('Enter')
            
            # Faster wait for results
            await asyncio.sleep(SEARCH_WAIT_TIME)
            
            # Quick check for no results
            try:
                no_results = await page.wait_for_selector(SELECTORS["no_results"], timeout=1000)  # Reduced timeout
                if no_results:
                    self.logger.warning(f"No results found for subscription: {subscription_id}")
                    return []
            except PlaywrightTimeoutError:
                pass
            
            # Wait for results table with shorter timeout
            try:
                await page.wait_for_selector(SELECTORS["results_table"], timeout=ELEMENT_TIMEOUT)
            except PlaywrightTimeoutError:
                self.logger.warning(f"Results table not found for {subscription_id}")
                return []
            table = await page.query_selector(SELECTORS["results_table"])
            
            if not table:
                return []
            
            rows = await table.query_selector_all(SELECTORS["table_rows"])
            all_results = []
            
            for row_index, row in enumerate(rows[1:], 1):  # Skip header
                try:
                    cells = await row.query_selector_all(SELECTORS["table_cells"])
                    if len(cells) < 6:
                        continue
                    
                    cell_texts = []
                    for cell in cells:
                        text = await cell.inner_text()
                        cleaned_text = text.strip().replace('\n', ' ').replace('\r', ' ')
                        cleaned_text = ' '.join(cleaned_text.split())
                        cell_texts.append(cleaned_text)
                    
                    # Check if this row matches our search
                    row_text = " ".join(cell_texts).lower()
                    if subscription_id.lower() in row_text:
                        data = {
                            "result_id": cell_texts[1] if len(cell_texts) > 1 else f"{subscription_id}_row_{row_index}",
                            "sitename": cell_texts[2] if len(cell_texts) > 2 else "",
                            "edison_lite_id": cell_texts[3] if len(cell_texts) > 3 else "",
                            "state": cell_texts[4] if len(cell_texts) > 4 else "",
                            "assigned_team": cell_texts[5] if len(cell_texts) > 5 else "",
                            "webcomponent_version": cell_texts[6] if len(cell_texts) > 6 else "",
                            "is_live": cell_texts[7] if len(cell_texts) > 7 else "",
                            "updated_at": cell_texts[8] if len(cell_texts) > 8 else ""
                        }
                        
                        all_results.append(data)
                
                except Exception as row_error:
                    self.logger.debug(f"Error processing row {row_index}: {row_error}")
                    continue
            
            return all_results
            
        except Exception as e:
            self.logger.error(f"Failed to scrape subscription {subscription_id}: {e}")
            return []
    
    def save_subscription_data(self, subscription_id: str, results: List[Dict[str, str]], session_id: int = None):
        """Save scraped data to database with session tracking."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        
        try:
            # Check if subscription exists
            cursor.execute('SELECT id FROM subscriptions WHERE subscription_search = ?', (subscription_id,))
            row = cursor.fetchone()
            
            if row:
                subscription_db_id = row[0]
                # Update existing subscription
                cursor.execute('''
                    UPDATE subscriptions 
                    SET last_scraped = ?, total_results = ?, status = ?, session_id = ?
                    WHERE id = ?
                ''', (get_ist_timestamp(), len(results), 'completed', session_id, subscription_db_id))
                
                # Delete old results for this session (if session_id exists) or all old results
                if session_id:
                    cursor.execute('DELETE FROM subscription_results WHERE subscription_id = ? AND session_id = ?', 
                                 (subscription_db_id, session_id))
                else:
                    cursor.execute('DELETE FROM subscription_results WHERE subscription_id = ?', (subscription_db_id,))
            else:
                # Create new subscription
                cursor.execute('''
                    INSERT INTO subscriptions (subscription_search, last_scraped, total_results, status, session_id)
                    VALUES (?, ?, ?, ?, ?)
                ''', (subscription_id, get_ist_timestamp(), len(results), 'completed', session_id))
                subscription_db_id = cursor.lastrowid
            
            # Insert results
            for result in results:
                cursor.execute('''
                    INSERT INTO subscription_results 
                    (subscription_id, session_id, result_id, sitename, edison_lite_id, state, 
                     assigned_team, webcomponent_version, is_live, updated_at, scraped_timestamp)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ''', (subscription_db_id, session_id, result['result_id'], result['sitename'], 
                     result['edison_lite_id'], result['state'], result['assigned_team'],
                     result['webcomponent_version'], result['is_live'], result['updated_at'], get_ist_timestamp()))
            
            conn.commit()
            self.logger.info(f"Saved {len(results)} results for {subscription_id}")
            
        except Exception as e:
            self.logger.error(f"Failed to save data for {subscription_id}: {e}")
        finally:
            conn.close()
    
    async def scrape_subscription_batch(self, subscription_batch: List[str], browser) -> List[tuple]:
        """Scrape multiple subscriptions in parallel using multiple browser tabs."""
        tasks = []
        results = []
        
        # Create multiple pages for parallel processing
        context = browser.contexts[0]
        
        for i, subscription_id in enumerate(subscription_batch):
            page = await context.new_page()
            page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)
            page.set_default_timeout(ELEMENT_TIMEOUT)
            
            # Block resources for speed in headless mode
            if browser._impl_obj._options.get('headless', True):
                await page.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
            
            is_first_search = (i == 0)  # Only first page handles auth
            task = self.scrape_subscription_data(subscription_id, page, is_first_search)
            tasks.append((subscription_id, task, page))
        
        # Execute all tasks in parallel
        for subscription_id, task, page in tasks:
            try:
                result = await task
                results.append((subscription_id, result, None))
            except Exception as e:
                self.logger.error(f"Failed to scrape {subscription_id}: {e}")
                results.append((subscription_id, [], str(e)))
            finally:
                await page.close()
        
        return results

    async def run_scraping_session_fast(self, headless: bool = True, batch_size: int = 3):
        """Run a fast scraping session with parallel processing."""
        if not PLAYWRIGHT_AVAILABLE:
            self.update_scraping_status(False, message="Playwright not available")
            return {"success": False, "message": "Playwright not available"}
        
        subscription_ids = self.read_subscription_ids()
        if not subscription_ids:
            self.update_scraping_status(False, message="No subscriptions found")
            return {"success": False, "message": "No subscriptions found in subscription.txt"}
        
        # Create a new scraping session
        session_id = self.create_scraping_session(len(subscription_ids))
        
        browser_mode = "fast parallel" if headless else "visible (manual login)"
        self.update_scraping_status(True, 0, len(subscription_ids), "", f"Starting {browser_mode} mode...")
        
        try:
            async with async_playwright() as p:
                # Launch browser with speed optimizations
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-features=TranslateUI',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-extensions'
                    ] if headless else [
                        '--disable-web-security',
                        '--disable-extensions'
                    ]
                )
                
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    bypass_csp=True,
                    java_script_enabled=True
                )
                
                successful_scrapes = 0
                failed_scrapes = 0
                
                # Process subscriptions in batches for parallel processing
                for batch_start in range(0, len(subscription_ids), batch_size):
                    batch_end = min(batch_start + batch_size, len(subscription_ids))
                    batch = subscription_ids[batch_start:batch_end]
                    
                    self.update_scraping_status(
                        True, batch_start, len(subscription_ids), f"Batch {batch_start//batch_size + 1}", 
                        f"Processing batch of {len(batch)} subscriptions..."
                    )
                    
                    # Process batch in parallel
                    batch_results = await self.scrape_subscription_batch(batch, browser)
                    
                    # Save results and update progress
                    for subscription_id, results, error in batch_results:
                        if error:
                            failed_scrapes += 1
                            self.logger.error(f"Failed to process {subscription_id}: {error}")
                        else:
                            self.save_subscription_data(subscription_id, results, session_id)
                            successful_scrapes += 1
                        
                        # Update progress for each completed subscription
                        current_progress = batch_start + (successful_scrapes + failed_scrapes - (batch_start // batch_size) * batch_size)
                        self.update_scraping_status(
                            True, current_progress, len(subscription_ids), subscription_id, 
                            f"Completed {subscription_id} - {len(results)} results"
                        )
                
                await browser.close()
                
                # Update final status
                self.update_scraping_status(
                    False, len(subscription_ids), len(subscription_ids), "", 
                    f"Fast scraping completed! {successful_scrapes} successful, {failed_scrapes} failed"
                )
                
                # Update scraping session with results
                session_notes = f"Fast scraping completed. {successful_scrapes} successful, {failed_scrapes} failed"
                self.update_scraping_session(session_id, successful_scrapes, failed_scrapes, session_notes)
                
                return {
                    "success": True,
                    "message": f"Fast scraping completed. {successful_scrapes} successful, {failed_scrapes} failed",
                    "successful": successful_scrapes,
                    "failed": failed_scrapes,
                    "mode": "fast_parallel"
                }
                
        except Exception as e:
            self.logger.error(f"Fast scraping session failed: {e}")
            self.update_scraping_status(False, message=f"Error: {str(e)}")
            # Update session with error
            self.update_scraping_session(session_id, 0, 0, f"Error: {str(e)}")
            return {"success": False, "message": f"Fast scraping failed: {str(e)}"}

    async def run_scraping_session(self, headless: bool = True, fast_mode: bool = False):
        """Run a complete scraping session."""
        if not PLAYWRIGHT_AVAILABLE:
            self.update_scraping_status(False, message="Playwright not available")
            return {"success": False, "message": "Playwright not available"}
        
        subscription_ids = self.read_subscription_ids()
        if not subscription_ids:
            self.update_scraping_status(False, message="No subscriptions found")
            return {"success": False, "message": "No subscriptions found in subscription.txt"}
        
        # Create a new scraping session
        session_id = self.create_scraping_session(len(subscription_ids))
        
        browser_mode = "headless" if headless else "visible"
        self.update_scraping_status(True, 0, len(subscription_ids), "", f"Starting {browser_mode} browser...")
        
        try:
            async with async_playwright() as p:
                # Launch browser with speed optimizations
                browser = await p.chromium.launch(
                    headless=headless,
                    args=[
                        '--no-sandbox',
                        '--disable-setuid-sandbox',
                        '--disable-dev-shm-usage',
                        '--disable-background-timer-throttling',
                        '--disable-backgrounding-occluded-windows',
                        '--disable-renderer-backgrounding',
                        '--disable-features=TranslateUI',
                        '--disable-web-security',
                        '--disable-features=VizDisplayCompositor',
                        '--disable-extensions'
                    ] if headless else [
                        '--disable-web-security',
                        '--disable-extensions'
                    ]
                )
                
                # Create context with speed optimizations
                context = await browser.new_context(
                    viewport={'width': 1920, 'height': 1080},
                    user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                    # Disable images and CSS for faster loading
                    bypass_csp=True,
                    java_script_enabled=True
                )
                
                # Block unnecessary resources for speed
                if headless:
                    await context.route("**/*.{png,jpg,jpeg,gif,svg,css,woff,woff2}", lambda route: route.abort())
                
                page = await context.new_page()
                
                # Set faster navigation timeout
                page.set_default_navigation_timeout(PAGE_LOAD_TIMEOUT)
                page.set_default_timeout(ELEMENT_TIMEOUT)
                
                successful_scrapes = 0
                failed_scrapes = 0
                
                # If not headless, give user time to manually login
                if not headless:
                    self.update_scraping_status(
                        True, 0, len(subscription_ids), "", 
                        "Browser opened - Please login manually, then scraping will start in 30 seconds..."
                    )
                    
                    # Navigate to login page and wait for user
                    await page.goto(DASHBOARD_URL, timeout=PAGE_LOAD_TIMEOUT)
                    await asyncio.sleep(30)  # Give user time to login
                
                for i, subscription_id in enumerate(subscription_ids):
                    self.update_scraping_status(
                        True, i, len(subscription_ids), subscription_id, 
                        f"Scraping {subscription_id}..."
                    )
                    
                    try:
                        # Pass is_first_search=True for the first subscription to handle auth
                        is_first_search = (i == 0) and headless  # Only auto-auth in headless mode
                        results = await self.scrape_subscription_data(subscription_id, page, is_first_search)
                        self.save_subscription_data(subscription_id, results, session_id)
                        successful_scrapes += 1
                        
                        self.update_scraping_status(
                            True, i + 1, len(subscription_ids), subscription_id, 
                            f"Completed {subscription_id} - {len(results)} results"
                        )
                        
                        # Shorter wait between searches for speed
                        await asyncio.sleep(BETWEEN_SEARCHES_WAIT)
                        
                    except Exception as e:
                        self.logger.error(f"Failed to process {subscription_id}: {e}")
                        failed_scrapes += 1
                
                if not headless:
                    # Keep browser open for a few seconds so user can see results
                    await asyncio.sleep(5)
                
                await browser.close()
                
                # Update final status
                self.update_scraping_status(
                    False, len(subscription_ids), len(subscription_ids), "", 
                    f"Completed! {successful_scrapes} successful, {failed_scrapes} failed"
                )
                
                # Update scraping session with results
                session_notes = f"Scraping completed. {successful_scrapes} successful, {failed_scrapes} failed"
                self.update_scraping_session(session_id, successful_scrapes, failed_scrapes, session_notes)
                
                return {
                    "success": True,
                    "message": f"Scraping completed. {successful_scrapes} successful, {failed_scrapes} failed",
                    "successful": successful_scrapes,
                    "failed": failed_scrapes
                }
                
        except Exception as e:
            self.logger.error(f"Scraping session failed: {e}")
            self.update_scraping_status(False, message=f"Error: {str(e)}")
            # Update session with error
            self.update_scraping_session(session_id, successful_scrapes, failed_scrapes, f"Error: {str(e)}")
            return {"success": False, "message": f"Scraping failed: {str(e)}"}
    
    def start_scraping_thread(self, headless: bool = True, fast_mode: bool = False):
        """Start scraping in a background thread with optional fast mode."""
        if scraping_status["is_running"]:
            return {"success": False, "message": "Scraping already in progress"}
        
        def run_async_scraping():
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                loop.run_until_complete(self.run_scraping_session(headless, fast_mode))
            finally:
                loop.close()
        
        thread = threading.Thread(target=run_async_scraping)
        thread.daemon = True
        thread.start()
        
        mode_text = "fast parallel" if fast_mode else ("headless" if headless else "visible (manual login)")
        return {"success": True, "message": f"Scraping started in {mode_text} mode"}


# Initialize data viewer
viewer = DataViewer()


@app.route('/')
def index():
    """Main dashboard page."""
    return render_template_string(HTML_TEMPLATE)


@app.route('/api/stats')
def api_stats():
    """API endpoint for statistics."""
    return jsonify(viewer.get_latest_session_stats())


@app.route('/api/data')
def api_data():
    """API endpoint for all data."""
    return jsonify(viewer.get_all_data())


@app.route('/api/export/json')
def api_export_json():
    """Export data as JSON file."""
    data = viewer.export_to_json()
    
    # Save to file
    filename = f"scraper_data_export_{get_ist_now().strftime('%Y%m%d_%H%M%S')}.json"
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    
    return send_file(filename, as_attachment=True, download_name=filename)


@app.route('/api/export/csv')
def api_export_csv():
    """Export data as CSV file."""
    import tempfile
    import os
    
    csv_data = viewer.export_to_csv()
    
    # Create temporary file
    fd, temp_path = tempfile.mkstemp(suffix='.csv')
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as tmp_file:
            tmp_file.write(csv_data)
        
        filename = f"scraper_data_export_{get_ist_now().strftime('%Y%m%d_%H%M%S')}.csv"
        return send_file(temp_path, as_attachment=True, download_name=filename)
    finally:
        # Clean up temp file after sending
        pass


@app.route('/api/scraping/status')
def api_scraping_status():
    """Get current scraping status."""
    return jsonify(scraping_status)


@app.route('/api/scraping/start', methods=['POST'])
def api_start_scraping():
    """Start a new scraping session."""
    # Get mode from request (default to headless)
    data = request.get_json() if request.is_json else {}
    headless = data.get('headless', True)
    fast_mode = data.get('fast_mode', False)
    
    result = viewer.start_scraping_thread(headless, fast_mode)
    return jsonify(result)


@app.route('/api/scraping/start-fast', methods=['POST'])
def api_start_scraping_fast():
    """Start fast parallel scraping session."""
    result = viewer.start_scraping_thread(headless=True, fast_mode=True)
    return jsonify(result)


@app.route('/api/scraping/start-manual', methods=['POST'])
def api_start_scraping_manual():
    """Start scraping with manual login (visible browser)."""
    result = viewer.start_scraping_thread(headless=False, fast_mode=False)
    return jsonify(result)


@app.route('/api/scraping/subscriptions')
def api_get_subscriptions():
    """Get list of subscriptions from file."""
    subscriptions = viewer.read_subscription_ids()
    return jsonify({
        "subscriptions": subscriptions,
        "count": len(subscriptions),
        "file": SUBSCRIPTION_FILE
    })


if __name__ == '__main__':
    print("🔥 Starting Modern Data Viewer")
    print("=" * 40)
    
    # Clear all existing data for a fresh start
    print("🧹 Clearing existing data...")
    viewer.clear_all_data()
    print("✅ Data cleared successfully")
    
    print("🌐 Open your browser to: http://localhost:8080")
    print("📊 Features:")
    print("  - Real-time dashboard")
    print("  - Search & filtering")
    print("  - JSON/CSV exports")
    print("  - API endpoints")
    print("=" * 40)
    
    app.run(host='0.0.0.0', port=8080, debug=True)
