# 🔗 Integrações - Setup Guide

Este documento descreve como integrar serviços externos com o Mr.Holmes CRM.

## 📱 WhatsApp (Twilio)

### 1. Setup Twilio

```bash
# Instalar Twilio SDK
pip install twilio

# Criar conta em https://www.twilio.com/console
# 1. Sign up e verify email
# 2. Create API Key
# 3. Get Account SID e Auth Token
# 4. Get WhatsApp Sandbox number
```

### 2. Configurar Variáveis de Ambiente

```bash
# .env
TWILIO_ACCOUNT_SID=your_account_sid
TWILIO_AUTH_TOKEN=your_auth_token
TWILIO_WHATSAPP_FROM=+55 11 98765-4321
TWILIO_WEBHOOK_URL=https://yourdomain.com/webhooks/whatsapp
```

### 3. Implementação no Backend

```python
# Em crm_backend.py ou crm_api.py

from twilio.rest import Client
from twilio.twiml.messaging_response import MessagingResponse

def send_whatsapp_message(to_number: str, message_body: str):
    """Send WhatsApp message via Twilio"""
    client = Client(
        os.getenv("TWILIO_ACCOUNT_SID"),
        os.getenv("TWILIO_AUTH_TOKEN")
    )
    
    message = client.messages.create(
        from_=f"whatsapp:{os.getenv('TWILIO_WHATSAPP_FROM')}",
        body=message_body,
        to=f"whatsapp:{to_number}"
    )
    return message.sid

@app.post("/webhooks/whatsapp")
async def receive_whatsapp(request: Request):
    """Receive incoming WhatsApp messages"""
    # Verify request signature
    twilio_signature = request.headers.get('X-Twilio-Signature')
    
    # Process message
    from_number = request.form.get('From')
    message_body = request.form.get('Body')
    
    # Create ticket in CRM
    ticket = create_ticket(
        customer_phone=from_number,
        subject=f"WhatsApp: {message_body[:50]}",
        channel="WhatsApp",
        body=message_body
    )
    
    # Send confirmation
    response = MessagingResponse()
    response.message("Mensagem recebida. Ticket #" + ticket.id + " criado.")
    
    return response
```

### 4. Webhook Setup

```bash
# Twilio Console > Messaging > Settings > WhatsApp Sandbox
# Webhook URL: https://yourdomain.com/webhooks/whatsapp
# HTTP POST

# Exemplo de curl para testar
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -d "From=whatsapp:+5511987654321" \
  -d "Body=Olá, teste de mensagem"
```

---

## 📧 Email (SendGrid)

### 1. Setup SendGrid

```bash
# Instalar SDK
pip install sendgrid

# Criar conta em https://sendgrid.com
# 1. Sign up
# 2. Create API Key
# 3. Verify sender email
```

### 2. Configurar Variáveis de Ambiente

```bash
# .env
SENDGRID_API_KEY=your_api_key
SENDGRID_FROM_EMAIL=noreply@yourdomain.com

# Para receber emails (inbound parse)
SENDGRID_INBOUND_PARSE_URL=https://yourdomain.com/webhooks/email
```

### 3. Implementação

```python
# Em crm_backend.py

from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, To

def send_email(to_email: str, subject: str, html_content: str):
    """Send email via SendGrid"""
    sg = SendGridAPIClient(os.getenv("SENDGRID_API_KEY"))
    
    message = Mail(
        from_email=os.getenv("SENDGRID_FROM_EMAIL"),
        to_emails=to_email,
        subject=subject,
        html_content=html_content
    )
    
    try:
        response = sg.send(message)
        return response.status_code == 202
    except Exception as e:
        logger.error(f"SendGrid error: {e}")
        return False

@app.post("/webhooks/email")
async def receive_email(request: Request):
    """Receive incoming emails"""
    # SendGrid inbound parse webhook
    
    from_email = request.form.get('from')
    subject = request.form.get('subject')
    text = request.form.get('text')
    
    # Create ticket
    ticket = create_ticket(
        customer_email=from_email,
        subject=subject,
        channel="Email",
        body=text
    )
    
    return {"status": "received", "ticket_id": ticket.id}
```

---

## 💬 Slack

### 1. Setup Slack App

```bash
# Criar app em https://api.slack.com/apps
# 1. Click "Create New App"
# 2. Choose "From scratch"
# 3. Enable Incoming Webhooks
# 4. Create Webhook URL
```

### 2. Configurar

```bash
# .env
SLACK_WEBHOOK_URL=https://hooks.slack.com/services/YOUR/WEBHOOK/URL
SLACK_BOT_TOKEN=xoxb-your-bot-token
SLACK_CHANNEL=#crm-alerts
```

### 3. Implementação

```python
# Em crm_backend.py

import requests

def send_slack_notification(message: str, channel: str = None):
    """Send Slack notification"""
    webhook_url = os.getenv("SLACK_WEBHOOK_URL")
    
    data = {
        "text": message,
        "channel": channel or os.getenv("SLACK_CHANNEL"),
        "username": "Mr.Holmes CRM"
    }
    
    response = requests.post(webhook_url, json=data)
    return response.status_code == 200

# Usar em eventos importantes
def on_ticket_created(ticket):
    send_slack_notification(
        f"🎫 Novo ticket: {ticket.subject}\n"
        f"Cliente: {ticket.customer}\n"
        f"Prioridade: {ticket.priority}"
    )
```

---

## 🔗 Zapier

### 1. Setup

```bash
# No Zapier:
# 1. Create Zap
# 2. Choose trigger (e.g., Form submission, Calendar event)
# 3. Choose action: Webhook
# 4. URL: https://yourdomain.com/webhooks/zapier
# 5. Method: POST
```

### 2. Implementação

```python
# Em crm_api.py

@app.post("/webhooks/zapier")
async def zapier_webhook(payload: Dict[str, Any]):
    """Receive data from Zapier"""
    # Create customer, ticket, or deal based on payload
    
    entity_type = payload.get("type")
    data = payload.get("data")
    
    if entity_type == "customer":
        customer = create_customer(**data)
    elif entity_type == "ticket":
        ticket = create_ticket(**data)
    elif entity_type == "deal":
        deal = create_deal(**data)
    
    return {"status": "processed"}
```

---

## 📊 Google Calendar

### 1. Setup OAuth

```bash
# Instalar SDK
pip install google-auth-oauthlib google-auth-httplib2 google-api-python-client

# Create credentials in Google Cloud Console
# 1. Create project
# 2. Enable Calendar API
# 3. Create OAuth 2.0 credentials (Desktop app)
# 4. Download JSON
```

### 2. Implementação

```python
from google.auth.transport.requests import Request
from google.oauth2.service_account import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

def create_calendar_event(title: str, start_time: str, attendees: list):
    """Create event in Google Calendar"""
    credentials = Credentials.from_service_account_file('credentials.json')
    service = build('calendar', 'v3', credentials=credentials)
    
    event = {
        'summary': title,
        'start': {
            'dateTime': start_time,
            'timeZone': 'America/Sao_Paulo',
        },
        'end': {
            'dateTime': calculate_end_time(start_time),
            'timeZone': 'America/Sao_Paulo',
        },
        'attendees': [{'email': email} for email in attendees],
    }
    
    event = service.events().insert(calendarId='primary', body=event).execute()
    return event.get('id')
```

---

## 🧪 Testando Integrações

### Teste Local com Ngrok

```bash
# Instalar ngrok
# https://ngrok.com/download

# Rodar ngrok
./ngrok http 8000

# URL pública: https://random-id.ngrok.io

# Usar em webhooks
# Twilio: https://random-id.ngrok.io/webhooks/whatsapp
# SendGrid: https://random-id.ngrok.io/webhooks/email
```

### Curl para Testar

```bash
# WhatsApp
curl -X POST http://localhost:8000/webhooks/whatsapp \
  -d "From=whatsapp:+5511987654321" \
  -d "Body=Mensagem de teste"

# Email
curl -X POST http://localhost:8000/webhooks/email \
  -F "from=cliente@example.com" \
  -F "subject=Test subject" \
  -F "text=Test email body"

# Slack
curl -X POST http://localhost:8000/webhooks/slack \
  -H "Content-Type: application/json" \
  -d '{"text": "Test notification"}'
```

---

## ✅ Checklist de Implementação

- [ ] Twilio WhatsApp setup
- [ ] SendGrid email setup
- [ ] Slack notifications
- [ ] Zapier integration
- [ ] Google Calendar sync
- [ ] Ngrok testing
- [ ] Production webhook URLs
- [ ] SSL certificate for webhooks
- [ ] Monitoring de falhas de webhook
- [ ] Logs de integrações
- [ ] Alertas de falhas

---

## 🚨 Troubleshooting

### Webhook não recebe dados

```bash
# Check webhook URL
curl https://yourdomain.com/webhooks/whatsapp

# View logs
docker-compose logs -f api

# Test com ngrok
./ngrok http 8000
# Use ngrok URL nos webhooks
```

### Autenticação falha

```bash
# Verificar credenciais em .env
cat .env | grep TWILIO_

# Regenerar tokens/keys
# Twilio: https://www.twilio.com/console/account/settings
# SendGrid: https://app.sendgrid.com/settings/api_keys
```

### Rate limiting

```python
# Implementar retry com backoff
import time

def send_whatsapp_with_retry(to_number, message, max_retries=3):
    for attempt in range(max_retries):
        try:
            return send_whatsapp_message(to_number, message)
        except Exception as e:
            if attempt < max_retries - 1:
                wait_time = 2 ** attempt  # Exponential backoff
                time.sleep(wait_time)
            else:
                raise
```

---

**Last Updated**: 2026-05-25
**Version**: 1.0.0
