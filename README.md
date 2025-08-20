# Lite Site Web Scrapper

A lightweight web scraping tool designed to monitor and collect data from Pfizer Webbuilder Dashboard and subscription websites. This tool provides automated data collection with a modern web interface for viewing and managing scraped data.

## Features

- **Automated Web Scraping**: Scrape data from multiple websites using Playwright
- **Real-time Data Viewing**: Modern web interface for viewing scraped data
- **Search and Filtering**: Find specific data quickly
- **JSON API Endpoints**: RESTful API for data access
- **Export Capabilities**: Export data in various formats
- **Statistics Dashboard**: View scraping statistics and insights
- **Database Management**: SQLite database with utility functions
- **Subscription Management**: Monitor multiple websites from a subscription list

## Project Structure

```
lite_site_web_scrapper/
├── webbuilder_scraper.py    # Main scraper application with web interface
├── db_utils.py              # Database management utilities
├── requirements.txt         # Python dependencies
├── subscription.txt         # List of websites to monitor
├── scraper_data.db         # SQLite database (created after first run)
├── result.csv              # CSV export of scraped data
├── data_viewer.log         # Application logs
└── README.md               # This file
```

## Installation

### Prerequisites

- Python 3.7 or higher
- pip (Python package installer)

### Step 1: Create a Virtual Environment

It's recommended to use a virtual environment to avoid conflicts with other Python projects.

#### For Mac/Linux:
```bash
# Create virtual environment
python3 -m venv venv

# Activate virtual environment
source venv/bin/activate
```

#### For Windows:
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment (Command Prompt)
venv\Scripts\activate

# Or for PowerShell
venv\Scripts\Activate.ps1
```

**Note**: You'll see `(venv)` in your terminal prompt when the virtual environment is active.

### Step 2: Install Dependencies

   ```bash
   pip install -r requirements.txt
   ```

### Step 3: Install Playwright Browsers

   ```bash
   playwright install
   ```

## Usage

### Starting the Web Interface

1. **Run the main application**:
   ```bash
   python webbuilder_scraper.py
   ```

2. **Open your browser and navigate to**:
   ```
   http://localhost:8080
   ```
3. **For fetching Abobe Analytics Data**:
   ```bash
   python adobe_analytics_tester.py
   ```

The web interface provides:
- Dashboard with scraping statistics
- Real-time data viewing
- Search and filtering capabilities
- Export functionality
- API endpoints

### Database Management

Use the database utilities to manage your scraped data:

```bash
# View database statistics
python db_utils.py stats

# Clear all data
python db_utils.py clear

# Remove duplicates
python db_utils.py duplicates

# Export data
python db_utils.py export

# Import data
python db_utils.py import
```

### Subscription Management

Edit `subscription.txt` to add or remove websites to monitor:

```plaintext
www.example1.com
www.example2.com
subdomain.example3.com
```

## Configuration

### Target URL

Update the dashboard URL in `webbuilder_scraper.py`:

```python
DASHBOARD_URL = "https://webbuilder.pfizer/webbuilder/dashboard/"
```

## API Endpoints

The application provides several API endpoints:

- `GET /api/data` - Get all scraped data
- `GET /api/stats` - Get scraping statistics
- `GET /api/export/csv` - Export data as CSV
- `GET /api/export/json` - Export data as JSON

## Database Schema

The SQLite database contains three main tables:

- **subscriptions**: Websites being monitored
- **subscription_results**: Scraped data results
- **scraping_sessions**: Scraping session metadata

## Dependencies

- **Python 3.7+**
- **Playwright**: Web automation and scraping
- **Flask**: Web framework for the interface
- **SQLite**: Database storage

## Logging

Application logs are saved to `data_viewer.log` with detailed information about:
- Scraping activities
- Database operations
- Web interface access
- Error messages
