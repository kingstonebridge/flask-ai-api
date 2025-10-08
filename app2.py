import requests
import smtplib
from email.mime.text import MIMEText
import time
import sqlite3
import logging
import json
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string

app = Flask(__name__)

# Configure logging to show in Render logs
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
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
        logger.info("✅ Database setup completed")
    
    def setup_apis(self):
        """API configuration"""
        self.headers = {
            'User-Agent': 'MoneyHunterBot/1.0',
            'Accept': 'application/json'
        }
        self.open_states_api_key = "bdffeea4-3bf8-4056-b6b3-2eab217221c6"
        logger.info("✅ APIs configured with OpenStates key")
    
    def search_government_apis(self, name, state):
        """Search government APIs for financial opportunities"""
        results = []
        
        try:
            logger.info(f"🔍 Starting search for '{name}' in {state}")
            
            # 1. USAspending.gov API
            usaspending_results = self.search_usaspending(name, state)
            results.extend(usaspending_results)
            logger.info(f"📊 USAspending results: {len(usaspending_results)}")
            
            # 2. Open States API with real key
            open_states_results = self.search_open_states(name, state)
            results.extend(open_states_results)
            logger.info(f"🏛️ Open States results: {len(open_states_results)}")
            
            # 3. Census API
            census_results = self.search_census_data(name, state)
            results.extend(census_results)
            logger.info(f"📈 Census results: {len(census_results)}")
            
            logger.info(f"🎯 TOTAL RESULTS FOUND: {len(results)}")
            
        except Exception as e:
            logger.error(f"❌ Government API search failed: {e}")
        
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
            
            logger.info(f"🌐 Calling USAspending API for '{name}' in {state}")
            response = requests.post(url, json=payload, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📥 USAspending API returned {len(data.get('results', []))} raw results")
                
                for recipient in data.get('results', []):
                    recipient_name = recipient.get('recipient_name', '')
                    if name.lower() in recipient_name.lower():
                        result = {
                            'name': recipient_name,
                            'address': f"{recipient.get('recipient_city', '')}, {recipient.get('recipient_state', '')}",
                            'amount': float(recipient.get('total_amount', 0)),
                            'source': 'Federal Contracts - USAspending.gov',
                            'state': state.upper()
                        }
                        results.append(result)
                        logger.info(f"💰 Found: {recipient_name} - ${result['amount']:,.2f}")
            
            logger.info(f"✅ USAspending found {len(results)} matching results")
            
        except Exception as e:
            logger.error(f"❌ USAspending search failed: {e}")
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
            
            logger.info(f"🌐 Calling OpenStates API for '{name}' in {state}")
            response = requests.get(url, params=params, headers=self.headers, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                raw_results = data.get('results', [])
                logger.info(f"📥 OpenStates API returned {len(raw_results)} raw results")
                
                for person in raw_results:
                    person_name = person.get('name', '')
                    current_address = person.get('current_address', {})
                    
                    address_parts = []
                    if current_address.get('street'):
                        address_parts.append(current_address['street'])
                    if current_address.get('city'):
                        address_parts.append(current_address['city'])
                    if current_address.get('state'):
                        address_parts.append(current_address['state'])
                    
                    formatted_address = ', '.join(address_parts) if address_parts else 'State Government'
                    
                    result = {
                        'name': person_name,
                        'address': formatted_address,
                        'amount': 0,
                        'source': f'{state} State Government - Open States',
                        'state': state.upper()
                    }
                    results.append(result)
                    logger.info(f"🏛️ Found government record: {person_name}")
            
            logger.info(f"✅ Open States found {len(results)} matching results")
            
        except Exception as e:
            logger.error(f"❌ Open States search failed: {e}")
        return results
    
    def search_census_data(self, name, state):
        """Search Census data"""
        results = []
        try:
            url = "https://api.census.gov/data/2017/abscb"
            params = {
                'get': 'NAME,EMP,PAYANN',
                'for': 'state:*',
                'NAME': f'*{name}*'
            }
            
            logger.info(f"🌐 Calling Census API for '{name}'")
            response = requests.get(url, params=params, timeout=15)
            
            if response.status_code == 200:
                data = response.json()
                logger.info(f"📥 Census API returned {len(data)} data rows")
                
                if len(data) > 1:
                    for business in data[1:]:  # Skip header
                        if len(business) >= 3:
                            business_name = business[0]
                            employees = business[1] if business[1] else '0'
                            payroll = business[2] if len(business) > 2 else '0'
                            
                            result = {
                                'name': business_name,
                                'address': f"Business in {state}",
                                'amount': float(payroll) if payroll and payroll.isdigit() else 0,
                                'source': 'US Census Business Data',
                                'state': state.upper()
                            }
                            results.append(result)
                            logger.info(f"📈 Found business: {business_name}")
            
            logger.info(f"✅ Census found {len(results)} matching results")
            
        except Exception as e:
            logger.error(f"❌ Census search failed: {e}")
        return results
    
    def generate_detailed_report(self, findings):
        """Generate detailed report and log it"""
        if not findings:
            report = "❌ No financial opportunities found today."
            logger.info(report)
            return report
        
        report_lines = [
            "💰 FINANCIAL OPPORTUNITY REPORT",
            "=" * 60,
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            ""
        ]
        
        total_value = 0
        for i, finding in enumerate(findings, 1):
            amount = finding.get('amount', 0)
            report_lines.append(f"{i}. {finding.get('name')}")
            report_lines.append(f"   📍 {finding.get('address', 'Location not specified')}")
            if amount > 0:
                report_lines.append(f"   💵 ${amount:,.2f}")
            else:
                report_lines.append(f"   💵 Informational (No amount specified)")
            report_lines.append(f"   📋 {finding.get('source')}")
            report_lines.append(f"   🗺️ {finding.get('state')}")
            report_lines.append("")
            total_value += amount
        
        if total_value > 0:
            report_lines.append(f"🎯 TOTAL POTENTIAL VALUE: ${total_value:,.2f}")
        else:
            report_lines.append(f"ℹ️ Informational findings only (no monetary value)")
        
        report_lines.append("\nNext steps: Visit official government websites for more information.")
        
        report = "\n".join(report_lines)
        
        # LOG THE ENTIRE REPORT TO RENDER LOGS
        logger.info("📨 REPORT GENERATED:\n" + report)
        
        return report
    
    def store_findings(self, findings):
        """Store findings in database"""
        cursor = self.conn.cursor()
        stored_count = 0
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
                stored_count += 1
            except Exception as e:
                logger.error(f"❌ Database insert failed: {e}")
        
        self.conn.commit()
        logger.info(f"💾 Stored {stored_count} findings in database")

# Initialize the bot
bot = MoneyHunterBot()

# HTML template for the web interface
HTML_TEMPLATE = '''
<!DOCTYPE html>
<html>
<head>
    <title>Money Hunter Bot</title>
    <style>
        body { font-family: Arial, sans-serif; max-width: 600px; margin: 40px auto; padding: 20px; }
        .form-group { margin-bottom: 15px; }
        label { display: block; margin-bottom: 5px; font-weight: bold; }
        input { width: 100%; padding: 10px; border: 1px solid #ddd; border-radius: 4px; }
        button { background: #007bff; color: white; padding: 12px 24px; border: none; border-radius: 4px; cursor: pointer; }
        .result { margin-top: 20px; padding: 15px; background: #f8f9fa; border-radius: 5px; white-space: pre-wrap; }
        .success { background: #d4edda; color: #155724; }
        .error { background: #f8d7da; color: #721c24; }
    </style>
</head>
<body>
    <h1>💰 Money Hunter Bot</h1>
    <p>Search for unclaimed assets and financial opportunities</p>
    
    <form method="post">
        <div class="form-group">
            <label>Full Name:</label>
            <input type="text" name="name" placeholder="e.g., John Smith or ABC Corporation" required>
        </div>
        
        <div class="form-group">
            <label>State (2-letter code):</label>
            <input type="text" name="state" placeholder="e.g., CA, NY, TX" required maxlength="2">
        </div>
        
        <div class="form-group">
            <label>Email (optional - for display only):</label>
            <input type="email" name="email" placeholder="your@email.com">
        </div>
        
        <button type="submit">Search Assets</button>
    </form>
    
    {% if result %}
    <div class="result {{ result_type }}">
        <h3>Search Results:</h3>
        {{ result }}
    </div>
    {% endif %}
</body>
</html>
'''

@app.route('/', methods=['GET', 'POST'])
def home():
    if request.method == 'POST':
        try:
            name = request.form.get('name', '').strip()
            state = request.form.get('state', '').strip().upper()
            email = request.form.get('email', '').strip()
            
            if not name or not state:
                return render_template_string(HTML_TEMPLATE, 
                    result="❌ Please fill in both Name and State fields", 
                    result_type="error")
            
            if len(state) != 2:
                return render_template_string(HTML_TEMPLATE,
                    result="❌ State must be 2-letter code (e.g., CA, NY, TX)",
                    result_type="error")
            
            logger.info(f"🎯 USER SEARCH: Name='{name}', State='{state}', Email='{email}'")
            
            # Perform searches
            findings = bot.search_government_apis(name, state)
            
            # Generate detailed report
            report = bot.generate_detailed_report(findings)
            
            # Store findings
            if findings:
                bot.store_findings(findings)
            
            # Display results to user
            display_result = f"🔍 Search completed for '{name}' in {state}\n\n"
            display_result += report
            display_result += f"\n\n📊 Found {len(findings)} total results"
            display_result += f"\n📋 Check Render logs for detailed API responses"
            
            return render_template_string(HTML_TEMPLATE, 
                result=display_result, 
                result_type="success")
            
        except Exception as e:
            error_msg = f"❌ Search error: {str(e)}"
            logger.error(error_msg)
            return render_template_string(HTML_TEMPLATE, 
                result=error_msg, 
                result_type="error")
    
    return render_template_string(HTML_TEMPLATE)

@app.route('/api/search', methods=['POST'])
def api_search():
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        state = data.get('state', '').strip().upper()
        
        if not name or not state:
            return jsonify({'error': 'Name and state are required'}), 400
        
        logger.info(f"🎯 API SEARCH: Name='{name}', State='{state}'")
        
        findings = bot.search_government_apis(name, state)
        report = bot.generate_detailed_report(findings)
        
        if findings:
            bot.store_findings(findings)
        
        return jsonify({
            'status': 'success',
            'findings_count': len(findings),
            'report': report,
            'total_value': sum(f.get('amount', 0) for f in findings)
        })
        
    except Exception as e:
        logger.error(f"❌ API search error: {e}")
        return jsonify({'error': 'Internal server error'}), 500

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'service': 'Money Hunter Bot'})

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    logger.info(f"🚀 Starting Money Hunter Bot on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
