

import os
from supabase import create_client, Client
from twilio.rest import Client as TwilioClient
from datetime import datetime, timezone
from dotenv import load_dotenv
load_dotenv()  # add this at the top after imports

# ========== ENVIRONMENT VARIABLES ==========
# Set these in Render dashboard or .env file
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://ytogcvqzqnzjfnxyqqip.supabase.co")
SUPABASE_KEY = os.getenv("SUPABASE_KEY","eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpc3MiOiJzdXBhYmFzZSIsInJlZiI6Inl0b2djdnF6cW56amZueHlxcWlwIiwicm9sZSI6ImFub24iLCJpYXQiOjE3NTYxODQxMzEsImV4cCI6MjA3MTc2MDEzMX0.HIdYgKaAPQ437yKCh0XFk7WQHK-bT_EMgEttmoLr7F0")  # Service role key
TWILIO_SID = os.getenv("TWILIO_SID")
TWILIO_AUTH_TOKEN = os.getenv("TWILIO_AUTH_TOKEN")
TWILIO_PHONE = os.getenv("TWILIO_PHONE")  # Twilio phone number
PHONE_NUMBER_1 = "number1"  # Replace with actual phone number for water_levels and water_levels2
PHONE_NUMBER_2 = "number2"  # Replace with actual phone number for water_levels3 and water_levels4

# Connect to Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Connect to Twilio
twilio_client = TwilioClient(TWILIO_SID, TWILIO_AUTH_TOKEN)

# ========== ALERT TRACKING ==========
# Track already sent alerts to avoid duplicates
sent_alerts = set()

# ========== ANOMALY RULES ==========
def is_anomalous(row: dict) -> bool:
    """Define anomaly detection rules here."""
    water_level = float(row.get("water_level") or 0)
    pressure = float(row.get("pressure") or 0)
    temperature = float(row.get("temperature") or 0)
    battery = float(row.get("battery_level") or 0)

    # Example anomaly rules (customize!)
    if water_level < 0 or water_level > 500:   # unrealistic values
        return True
    if pressure < 0 or pressure > 200000:
        return True
    if temperature < -10 or temperature > 70:  # sensor failure range
        return True
    if battery < 1:  # battery critically low
        return True
    return False

# ========== ALERTING ==========
def send_alert(table: str, row: dict):
    """Send SMS via Twilio."""
    # Create unique identifier for this alert
    alert_id = f"{table}_{row.get('station_id')}_{row.get('id')}"
    
    # Check if we've already sent an alert for this specific row
    if alert_id in sent_alerts:
        print(f"⏭️  Alert already sent for {alert_id}")
        return
    
    # Determine which phone number to use based on table
    if table in ["water_levels", "water_levels2"]:
        recipient_phone = "+918096191416"
    else:  # water_levels3, water_levels4
        recipient_phone = "+917601024711"
    
    message = f"""
    🚨 Anomaly Detected!
    Table: {table}
    Station ID: {row.get('station_id')}
    Time: {row.get('timestamp')}
    Values -> WL: {row.get('water_level')} | P: {row.get('pressure')} | T: {row.get('temperature')} | B: {row.get('battery_level')}
    """
    twilio_client.messages.create(
        body=message,
        from_=TWILIO_PHONE,
        to=recipient_phone
    )
    
    # Mark this alert as sent
    sent_alerts.add(alert_id)
    print(f"✅ Alert sent via Twilio for {alert_id} to {recipient_phone}")

# ========== POLLING LOOP ==========
def poll_tables():
    """Poll Supabase tables for new rows and check anomalies."""
    global last_poll_time
    last_poll_time = datetime.now()
    
    tables = ["water_levels", "water_levels2", "water_levels3", "water_levels4"]
    for table in tables:
        try:
            response = supabase.table(table).select("*").order("id", desc=True).limit(1).execute()
            if response.data:
                latest_row = response.data[0]
                if is_anomalous(latest_row):
                    send_alert(table, latest_row)
        except Exception as e:
            print(f"❌ Error polling {table}: {str(e)}")

# ========== FLASK WEB SERVICE ==========
from flask import Flask, jsonify
from datetime import datetime

app = Flask(__name__)
service_start_time = datetime.now()
monitoring_active = True
last_poll_time = None

@app.route('/')
def home():
    uptime = datetime.now() - service_start_time
    return jsonify({
        'service': 'Water Level Anomaly Detection',
        'status': 'running',
        'monitoring_active': monitoring_active,
        'uptime_seconds': int(uptime.total_seconds()),
        'alerts_sent_count': len(sent_alerts),
        'last_poll': last_poll_time.isoformat() if last_poll_time else 'Not started',
        'tables_monitored': ['water_levels', 'water_levels2', 'water_levels3', 'water_levels4']
    })

@app.route('/health')
def health():
    return jsonify({'status': 'healthy', 'timestamp': datetime.now().isoformat()})

@app.route('/alerts')
def alerts():
    return jsonify({
        'total_alerts_sent': len(sent_alerts),
        'alert_ids': list(sent_alerts),
        'monitoring_active': monitoring_active
    })

@app.route('/status')
def status():
    uptime = datetime.now() - service_start_time
    return jsonify({
        'service_status': 'active' if monitoring_active else 'paused',
        'uptime_hours': round(uptime.total_seconds() / 3600, 2),
        'last_poll': last_poll_time.isoformat() if last_poll_time else 'Never',
        'alerts_sent': len(sent_alerts)
    })

@app.route('/trigger-check')
def trigger_check():
    """Manually trigger a polling check."""
    try:
        poll_tables()
        return jsonify({
            'message': 'Manual check completed',
            'timestamp': datetime.now().isoformat(),
            'alerts_sent_count': len(sent_alerts)
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500

def start_monitoring():
    """Start the monitoring loop."""
    import time
    print("🔄 Starting anomaly detector service...")
    while True:
        if monitoring_active:
            poll_tables()
        time.sleep(100)  # Poll every 100 seconds

if __name__ == "__main__":
    import threading
    
    # Start monitoring in a separate thread
    monitor_thread = threading.Thread(target=start_monitoring, daemon=True)
    monitor_thread.start()
    
    # Start Flask web server
    port = int(os.environ.get('PORT', 10000))
    print(f"🚀 Starting Flask web service on port {port}")
    app.run(host='0.0.0.0', port=port, debug=False)
