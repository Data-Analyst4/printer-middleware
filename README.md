# 🖨️ Printer Middleware

**Enterprise-grade printer management system with async processing, persistent storage, and real-time monitoring**

[![Version](https://img.shields.io/badge/version-1.0.0-blue.svg)](https://github.com/yourusername/printer-middleware/releases)
[![Python](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](https://opensource.org/licenses/MIT)

## ✨ Features

- ✅ **Async API Layer** - Non-blocking job enqueuing with immediate response
- ✅ **Persistent Storage** - SQLite database for job persistence and printer management
- ✅ **Worker Processing System** - Multi-threaded workers per printer with connection pooling
- ✅ **Retry Engine** - Exponential backoff retry mechanism (5s → 30s → 2min → 10min)
- ✅ **Real-time Monitoring** - WebSocket support for live job and printer status updates
- ✅ **Production Server** - Waitress WSGI server for production deployment
- ✅ **Windows Service** - NSSM compatibility for auto-startup as Windows service
- ✅ **Comprehensive API** - RESTful endpoints for job management, printer monitoring, and metrics
- ✅ **Dashboard** - Web-based monitoring interface with real-time updates

---

## 📦 Installation

### Option 1: Install from Source

```bash
# Clone the repository
git clone https://github.com/yourusername/printer-middleware.git
cd printer-middleware

# Install dependencies
pip install -r requirements.txt
```

### Option 2: Install Specific Version

```bash
# Download specific version via git tags
git clone --branch v1.0.0 https://github.com/yourusername/printer-middleware.git

# Or download ZIP from GitHub releases
# https://github.com/yourusername/printer-middleware/releases/tag/v1.0.0
```

### Option 3: Install via pip (when published)

```bash
pip install printer-middleware==1.0.0
```

---

## 🚀 Quick Start

### 1. Configure Printers

Edit `config/printers.json`:

```json
{
  "P1": {
    "ip": "192.168.1.100",
    "port": 9100
  },
  "P2": {
    "ip": "192.168.1.101",
    "port": 9100
  }
}
```

### 2. Run the Server

```bash
# Development mode
python main.py --debug

# Production mode
python main.py

# Show version
python main.py --version
```

Server starts at `http://0.0.0.0:5000`

### 3. Access Dashboard

Open `http://localhost:5000` in your browser for the monitoring dashboard.

---

## 📋 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/print` | Submit print job (async) |
| GET | `/job/<id>` | Get job status |
| GET | `/jobs` | Get all jobs |
| GET | `/printers` | Get printer status |
| GET | `/metrics` | Get system metrics |
| GET | `/version` | Get version information |
| GET | `/health` | Health check |

### Example API Usage

```bash
# Submit a print job
curl -X POST http://localhost:5000/print \
  -H "Content-Type: application/json" \
  -d '{
    "printer_id": "P1",
    "commands": ["^XA^FO50,50^ADN,36,20^FDHello World^FS^XZ"]
  }'

# Response: {"job_id": "550e8400-e29b-41d4-a716-446655440000", "status": "queued"}

# Check job status
curl http://localhost:5000/job/550e8400-e29b-41d4-a716-446655440000
```

---

## 🏗️ Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   REST API      │    │  Job Queue      │    │   Workers       │
│   (Flask)       │───▶│  (SQLite)       │───▶│   (Threads)     │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   Dashboard     │    │   Metrics       │    │   Printers      │
│   (WebSocket)   │    │   (Real-time)   │    │   (TCP/IP)      │
└─────────────────┘    └─────────────────┘    └─────────────────┘
```

### Key Components

- **API Layer**: Async REST endpoints with immediate response
- **Job Manager**: Persistent job storage with retry logic
- **Worker System**: Multi-threaded processing per printer
- **Connection Manager**: Persistent TCP connections with auto-reconnect
- **Dashboard**: Real-time monitoring via WebSocket

---

## 🔄 Version Management

### Current Version: v1.0.0

This project uses [Semantic Versioning](https://semver.org/):

- **MAJOR** version for incompatible API changes
- **MINOR** version for backwards-compatible functionality additions
- **PATCH** version for backwards-compatible bug fixes

### Version History

See [CHANGELOG.md](CHANGELOG.md) for detailed version history.

### Downloading Specific Versions

#### Via Git Tags
```bash
# List all versions
git tag -l

# Download specific version
git clone --branch v1.0.0 https://github.com/yourusername/printer-middleware.git
cd printer-middleware

# Or checkout in existing repo
git checkout tags/v1.0.0
```

#### Via GitHub Releases
1. Go to [Releases](https://github.com/yourusername/printer-middleware/releases)
2. Download the ZIP file for your desired version
3. Extract and install dependencies

#### Via pip (when published to PyPI)
```bash
pip install printer-middleware==1.0.0
```

---

## 🛠️ Development

### Setting up Development Environment

```bash
# Clone repository
git clone https://github.com/yourusername/printer-middleware.git
cd printer-middleware

# Create virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Install in development mode
pip install -e .
```

### Running Tests

```bash
python -m pytest
```

### Building Distribution

```bash
# Build wheel and source distribution
python -m build

# Upload to PyPI (when ready)
twine upload dist/*
```

---

## 📚 Documentation

- [API Documentation](docs/api.md)
- [Deployment Guide](docs/deployment.md)
- [Configuration Guide](docs/configuration.md)
- [Troubleshooting](docs/troubleshooting.md)

---

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 🙋 Support

- 📧 **Email**: your.email@example.com
- 🐛 **Issues**: [GitHub Issues](https://github.com/yourusername/printer-middleware/issues)
- 📖 **Documentation**: [Wiki](https://github.com/yourusername/printer-middleware/wiki)

---

**Made with ❤️ for enterprise printing solutions**

### 4. Open Dashboard

Visit: `http://localhost:5000/`

---

## 📡 API Endpoints

### POST /print
Submit a print job (asynchronous, returns immediately)

**Single Command:**
```bash
curl -X POST http://localhost:5000/print \
  -H "Content-Type: application/json" \
  -d '{
    "printer_id": "P1",
    "printer": {
      "ip": "192.168.1.100",
      "port": 9100
    },
    "command": {
      "command": "PRINT",
      "template": "label_template",
      "data": {"field": "value"}
    },
    "priority": "high"
  }'
```

**Multiple Commands:**
```bash
curl -X POST http://localhost:5000/print \
  -H "Content-Type: application/json" \
  -d '{
    "printer_id": "P1",
    "printer": {
      "ip": "192.168.1.100",
      "port": 9100
    },
    "commands": [
      {"command": "STAR", "templatename": "DEMO"},
      {"command": "DATA", "data": {"POD1": "123"}}
    ],
    "priority": "normal"
  }'
```

**Response:**
```json
{
  "success": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "status": "queued",
  "message": "Job queued successfully"
}
```

---

### GET /job/{job_id}
Get job status and responses

**Example:**
```bash
curl http://localhost:5000/job/550e8400-e29b-41d4-a716-446655440000
```

**Response:**
```json
{
  "success": true,
  "job_id": "550e8400-e29b-41d4-a716-446655440000",
  "printer_id": "P1",
  "status": "completed",
  "priority": "high",
  "commands": [
    {"command": "PRINT", "template": "label_template", "data": {"field": "value"}}
  ],
  "created_at": "2026-04-06T12:00:00.123456",
  "updated_at": "2026-04-06T12:00:05.654321",
  "responses": [
    "OK",
    "Template loaded"
  ],
  "error": null
}
```

**Status Values:** `queued | processing | completed | failed`

---

### GET /jobs
Get all jobs (paginated, last 100)

**Example:**
```bash
curl http://localhost:5000/jobs
```

**Response:**
```json
{
  "success": true,
  "jobs": [
    {
      "job_id": "550e8400-e29b-41d4-a716-446655440000",
      "printer_id": "P1",
      "status": "completed",
      "priority": "high",
      "created_at": "2026-04-06T12:00:00.123456",
      "updated_at": "2026-04-06T12:00:05.654321",
      "responses": ["OK"],
      "error": null
    }
  ]
}
```

---

### GET /printers
Get all registered printers and status

**Example:**
```bash
curl http://localhost:5000/printers
```

**Response:**
```json
{
  "P1": {
    "ip": "192.168.1.100",
    "port": 9100,
    "connection_status": "connected",
    "queue_size": 2
  },
  "P2": {
    "ip": "192.168.1.101",
    "port": 9100,
    "connection_status": "disconnected",
    "queue_size": 0
  }
}
```

**Connection Status:** `connected | disconnected`

---

### GET /metrics
Get system metrics

**Example:**
```bash
curl http://localhost:5000/metrics
```

**Response:**
```json
{
  "success": true,
  "total_jobs": 150,
  "queued_jobs": 5,
  "processing_jobs": 2,
  "completed_jobs": 140,
  "failed_jobs": 3
}
```

---

### GET /health
Health check endpoint

**Example:**
```bash
curl http://localhost:5000/health
```

**Response:**
```json
{
  "status": "healthy",
  "service": "printer-middleware"
}
```

---

## 🏗️ Architecture

```
printer-middleware/
├── main.py                              # Application entry point
├── config/
│   └── printers.json                   # Printer configuration
├── logs/
│   ├── app.log                         # Plain text logs
│   └── app.jsonl                       # Structured JSON logs
├── dashboard/
│   └── index.html                      # Monitoring dashboard (auto-refresh)
└── app/
    ├── api/
    │   └── routes.py                   # Flask routes & endpoints
    ├── models/
    │   └── job.py                      # Job model with status enum
    ├── services/
    │   ├── printer_manager.py          # Printer registration & job submission
    │   ├── connection_manager.py       # Persistent TCP connections
    │   ├── job_manager.py              # Job lifecycle & tracking
    │   ├── queue_worker.py             # Worker thread with retry logic
    │   └── printer_service.py          # Low-level socket communication
    └── utils/
        ├── validator.py                # Request validation
        └── logger.py                   # Structured logging (JSON + file)
```

---

## 📊 Dashboard

The dashboard provides **real-time monitoring** at `http://localhost:5000/`:

1. **System Metrics** - Total/queued/processing/completed/failed jobs
2. **Printer Status** - Connection status, queue size, IP/port
3. **Recent Jobs** - Last 10 jobs with status, priority, timestamps
4. **Auto-refresh** - Updates every 3 seconds

---

## 🧪 Testing

**Submit Job:**
```bash
JOB_ID=$(curl -s -X POST http://localhost:5000/print \
  -H "Content-Type: application/json" \
  -d '{
    "printer_id": "P1",
    "printer": {"ip": "192.168.1.100", "port": 9100},
    "command": {"command": "PRINT"},
    "priority": "high"
  }' | jq -r '.job_id')

echo "Job ID: $JOB_ID"
```

**Check Status:**
```bash
curl http://localhost:5000/job/$JOB_ID | jq
```

**Get All Metrics:**
```bash
curl http://localhost:5000/metrics | jq
```

---

## 📝 Logging

Logs are stored in two formats:

- **Plain text** (`logs/app.log`) - Human readable
- **Structured JSON** (`logs/app.jsonl`) - Machine parseable for centralized logging

Each log includes: timestamp, level, message, job_id, printer_id

---

## 🚨 Troubleshooting

| Issue | Solution |
|-------|----------|
| Printer not connecting | Verify IP/port in config, check network connectivity |
| Job stuck in queued | Check logs, verify printer online via `GET /printers` |
| Dashboard not loading | Ensure Flask running: `curl http://localhost:5000/` |
| Memory increasing | Monitor job count via `GET /metrics` |

---

## 📚 Example Workflows

### Python: Submit and Poll

```python
import requests
import time

# 1. Submit job
resp = requests.post('http://localhost:5000/print', json={
    "printer_id": "P1",
    "printer": {"ip": "192.168.1.100", "port": 9100},
    "command": {"command": "PRINT", "data": {"item": "123"}},
    "priority": "normal"
})
job_id = resp.json()['job_id']

# 2. Poll until complete
for _ in range(30):
    status = requests.get(f'http://localhost:5000/job/{job_id}').json()
    if status['status'] in ['completed', 'failed']:
        print(f"Job {status['status']}")
        break
    time.sleep(2)
```

### Priority Processing

High-priority jobs are processed first regardless of submission order.

---

## ✅ Production Checklist

- [ ] Configure printers in `config/printers.json`
- [ ] Set environment to production
- [ ] Enable HTTPS
- [ ] Add API authentication
- [ ] Set up log aggregation (ELK/Splunk)
- [ ] Configure alerting on failed jobs
- [ ] Test failover scenarios

---

## 📄 License

Proprietary - Production Printer Middleware
