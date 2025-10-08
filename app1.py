import os
import requests
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import time
import sqlite3
import logging
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template

app = Flask(__name__)

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class MoneyHunterBot:
    def __init__(self):
        self.setup_database()
        self.setup_apis()
    
    def setup_database(self):
        """Use SQLite for compatibility"""
        self.conn = sqlite3.connect('moneyhunter.db', check_same_thread=False)
        cursor = self.conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS findings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                address TEXT,
                amount REAL,
                source TEXT,
                state TEXT,
                found_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                reported BOOLEAN DEFAULT FALSE
            )
        ''')
        self.conn.commit()
        logger.info("Database setup completed")
    
    def setup_apis(self):
        """API configuration"""
        self.headers = {
            'User-Agent': 'MoneyHunterBot/1.0',
            'Accept': 'application/json'
        }
        self.open_states_api_key = "bdffeea4-3bf8-4056-b6b3-2eab217221c6"
    
    def search_government_apis(self, name, state):
        """Search government APIs for financial opportunities"""
        results = []
        
        try:
            # 1. USAspending.gov API
            usaspending_results = self.search_usaspending(name, state)
            results.extend(usaspending_results)
            
            # 2. Open States API with real key
            open_states_results = self.search_open_states(name, state)
            results.extend(open_states_results)
            
            # 3. Census API
            census_results = self.search_census_data(name, state)
            results.extend(census_results)
            
        except Exception as e:
            logger.error(f"Government API search failed: {e}")
        
        return results
    
    def search_usaspending(self, name, state):
        """Search USAspending.gov API"""
        results = []
        try:
            url = "https://api.usaspending.gov/api/v2/search/recipients/"
            payload = {
                "filters": {
                    "keyword": name,
                    "recipient_state": state.upper()
                },
                "limit": 10,
                "page": 1
            }
            
            response = requests.post(url, json=payload, headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for recipient in data.get('results', []):
                    if name.lower() in recipient.get('recipient_name', '').lower():
                        results.append({
                            'name': recipient.get('recipient_name'),
                            'address': f"{recipient.get('recipient_city', '')}, {recipient.get('recipient_state', '')}",
                            'amount': float(recipient.get('total_amount', 0)),
                            'source': 'Federal Contracts - USAspending.gov',
                            'state': state.upper()
                        })
            logger.info(f"USAspending found {len(results)} results")
        except Exception as e:
            logger.error(f"USAspending search failed: {e}")
        return results
    
    def search_open_states(self, name, state):
        """Search Open States API with real key"""
        results = []
        try:
            url = "https://v3.openstates.org/people"
            params = {
                'name': name,
                'state': state.lower(),
                'apikey': self.open_states_api_key
            }
            
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for person in data.get('results', []):
                    current_address = person.get('current_address', {})
                    address_parts = []
                    if current_address.get('street'):
                        address_parts.append(current_address['street'])
                    if current_address.get('city'):
                        address_parts.append(current_address['city'])
                    if current_address.get('state'):
                        address_parts.append(current_address['state'])
                    
                    formatted_address = ', '.join(address_parts) if address_parts else 'State Government'
                    
                    results.append({
                        'name': person.get('name', ''),
                        'address': formatted_address,
                        'amount': 0,
                        'source': f'{state} State Government - Open States',
                        'state': state.upper()
                    })
                logger.info(f"Open States found {len(results)} results")
        except Exception as e:
            logger.error(f"Open States search failed: {e}")
        return results
    
    def search_census_data(self, name, state):
        """Search Census data"""
        results = []
        try:
            # Simple census data search
            url = "https://api.census.gov/data/2017/abscb"
            params = {
                'get': 'NAME,EMP',
                'for': 'state:*',
                'NAME': f'*{name}*'
            }
            
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                if len(data) > 1:
                    for business in data[1:]:
                        if len(business) >= 2:
                            results.append({
                                'name': business[0],
                                'address': f"Business in {state}",
                                'amount': float(business[1]) if business[1] and business[1].isdigit() else 0,
                                'source': 'US Census Data',
                                'state': state.upper()
                            })
        except Exception as e:
            logger.error(f"Census search failed: {e}")
        return results
    
    def search_business_grants(self, business_type, location):
        """Search for business grants"""
        opportunities = []
        try:
            # SBA grants search
            url = "https://api.sba.gov/loans_grants.json"
            params = {'business_type': business_type}
            
            response = requests.get(url, params=params, timeout=15)
            if response.status_code == 200:
                data = response.json()
                for program in data[:3]:  # Limit to 3 results
                    opportunities.append({
                        'type': 'Business Grant',
                        'name': program.get('program_name', ''),
                        'amount': program.get('max_loan_amount', 'Varies'),
                        'deadline': 'Rolling',
                        'description': program.get('program_description', ''),
                        'eligibility': 'Small Business',
                        'location': location,
                        'source': 'SBA'
                    })
        except Exception as e:
            logger.error(f"Business grants search failed: {e}")
        return opportunities
    
    def send_email(self, email, report):
        """Send email with findings"""
        try:
            smtp_server = "smtp.gmail.com"
            port = 587
            sender_email = "jamalassker2032@gmail.com"
            password = "cbod cvec huka iltz"
            
            msg = MIMEMultipart()
            msg["Subject"] = f"💰 Financial Opportunities - {datetime.now().strftime('%Y-%m-%d')}"
            msg["From"] = sender_email
            msg["To"] = email
            
            msg.attach(MIMEText(report, 'plain'))
            
            with smtplib.SMTP(smtp_server, port) as server:
                server.starttls()
                server.login(sender_email, password)
                server.send_message(msg)
            
            logger.info(f"Email sent to {email}")
            return True
        except Exception as e:
            logger.error(f"Email failed: {e}")
            return False
    
    def generate_report(self, findings):
        """Generate report from findings"""
        if not findings:
            return "No financial opportunities found today. We'll continue monitoring."
        
        report = [
            "💰 FINANCIAL OPPORTUNITY REPORT",
            "=" * 50,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        total_value = 0
        for finding in findings:
            amount = finding.get('amount', 0)
            report.append(f"● {finding.get('name')}")
            report.append(f"  Location: {finding.get('address', 'Not specified')}")
            if amount > 0:
                report.append(f"  Amount: ${amount:,.2f}")
            report.append(f"  Source: {finding.get('source')}")
            report.append(f"  State: {finding.get('state')}")
            report.append("")
            total_value += amount
        
        if total_value > 0:
            report.append(f"TOTAL POTENTIAL VALUE: ${total_value:,.2f}")
        
        report.append("\nNext steps: Visit official government websites to claim.")
        return "\n".join(report)
    
    def store_findings(self, findings):
        """Store findings in database"""
        cursor = self.conn.cursor()
        for finding in findings:
            try:
                cursor.execute('''
                    INSERT OR IGNORE INTO findings 
                    (name, address, amount, source, state, found_date)
                    VALUES (?, ?, ?, ?, ?, ?)
                ''', (
                    finding.get('name'),
                    finding.get('address'),
                    finding.get('amount', 0),
                    finding.get('source'),
                    finding.get('state'),
                    datetime.now()
                ))
            except Exception as e:
                logger.error(f"Database insert failed: {e}")
        self.conn.commit()

# Initialize the bot
bot = MoneyHunterBot()

@app.route('/')
def home():
    return """
    <html>
        <head><title>Money Hunter Bot</title></head>
        <body>
            <h1>💰 Money Hunter Bot</h1>
            <p>Search for unclaimed assets and financial opportunities</p>
            <form action="/search" method="post">
                <input type="text" name="name" placeholder="Full Name" required><br>
                <input type="text" name="state" placeholder="State (e.g., CA)" required><br>
                <input type="email" name="email" placeholder="Email" required><br>
                <button type="submit">Search</button>
            </form>
        </body>
    </html>
    """

@app.route('/search', methods=['POST'])
def search():
    try:
        name = request.form.get('name', '').strip()
        state = request.form.get('state', '').strip()
        email = request.form.get('email', '').strip()
        
        if not name or not state or not email:
            return "Please fill all fields", 400
        
        logger.info(f"Searching for {name} in {state}")
        
        # Perform searches
        findings = bot.search_government_apis(name, state)
        
        # Generate and send report
        report = bot.generate_report(findings)
        
        if findings:
            bot.send_email(email, report)
            bot.store_findings(findings)
        
        return f"""
        <html>
            <body>
                <h2>Search Completed</h2>
                <p>Found {len(findings)} opportunities</p>
                <p>Report sent to {email}</p>
                <a href="/">Search Again</a>
            </body>
        </html>
        """
        
    except Exception as e:
        logger.error(f"Search error: {e}")
        return "An error occurred. Please try again.", 500

@app.route('/api/search', methods=['POST'])
def api_search():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        state = data.get('state', '').strip()
        email = data.get('email', '').strip()
        
        if not name or not state or not email:
            return jsonify({'error': 'Missing required fields'}), 400
        
        findings = bot.search_government_apis(name, state)
        report = bot.generate_report(findings)
        
        if findings:
            bot.send_email(email, report)
            bot.store_findings(findings)
        
        return jsonify({
            'status': 'success',
            'findings_count': len(findings),
            'message': f'Report sent to {email}'
        })
        
    except Exception as e:
        logger.error(f"API search error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'Money Hunter Bot'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
