# Wan S2V Flask API Server with R2 Integration

A Flask-based REST API server for processing Speech-to-Video (S2V) generation using the Wan 2.2 model with Cloudflare R2 storage integration and sequential processing queue.

## 🚀 Features

- **Sequential Processing**: One generation at a time to prevent GPU conflicts
- **R2 Integration**: Downloads input assets and uploads results to Cloudflare R2
- **Real-time Status**: Track progress through downloading, processing, and uploading stages  
- **Queue Management**: FIFO queue with position tracking and estimated wait times
- **Robust Error Handling**: Comprehensive error reporting and recovery
- **Clean Workspace**: Automatic cleanup of temporary files
- **Backend Compatible**: RESTful API designed for backend server integration

## 📋 System Requirements

- Python 3.10+
- GPU with CUDA support (for Wan model)
- Cloudflare R2 account and bucket access
- Wan 2.2 model checkpoints

## 🛠️ Installation

### 1. Install Dependencies

```bash
# Install Python dependencies
pip install -r requirements_r2_api.txt

# Or install core requirements separately:
pip install Flask Flask-CORS boto3 python-dotenv
```

### 2. Configure Environment

```bash
# Copy example environment file
cp .env.example .env

# Edit .env with your R2 credentials and configuration
nano .env
```

**Required Environment Variables:**
```bash
# Cloudflare R2 Configuration
R2_ENDPOINT_URL=https://your-account-id.r2.cloudflarestorage.com
R2_ACCESS_KEY_ID=your_r2_access_key
R2_SECRET_ACCESS_KEY=your_r2_secret_key
R2_OUTPUT_BUCKET=output-bucket

# Optional Configuration
R2_REGION=auto
R2_PUBLIC_DOMAIN=https://your-domain.r2.dev
WORKSPACE_DIR=workspace
CLEANUP_WORKSPACE=true
WAN_CKPT_DIR=./Wan2.2-S2V-14B/
```

### 3. Set Up Model Checkpoints

Ensure your Wan S2V 14B model checkpoints are available:
```bash
# Default location
./Wan2.2-S2V-14B/
```

## 🚀 Usage

### Start the Server

```bash
# Basic startup
python app.py

# Custom configuration
python app.py --host 0.0.0.0 --port 5000 --log-level INFO

# Production mode
python app.py --host 0.0.0.0 --port 5000 --log-level WARNING
```

### Health Check

```bash
curl http://localhost:5000/health
```

## 📡 API Reference

### Submit Processing Request

**POST** `/{user_id}/{request_id}`

Submit a new S2V generation request.

```bash
curl -X POST http://localhost:5000/user123/req001 \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "A beautiful sunset over the ocean",
    "image_r2_path": "input-bucket/images/user123/sunset.jpg",
    "audio_r2_path": "input-bucket/audio/user123/waves.wav",
    "size": "832*480",
    "sample_guide_scale": 4.0,
    "sample_steps": 20
  }'
```

**Response (202 Accepted):**
```json
{
  "message": "Request user123/req001 queued successfully",
  "status": "queued",
  "queue_position": 1,
  "estimated_wait_time_minutes": 5,
  "status_url": "/user123/req001/status"
}
```

### Check Request Status

**GET** `/{user_id}/{request_id}/status`

```bash
curl http://localhost:5000/user123/req001/status
```

**Response:**
```json
{
  "user_id": "user123",
  "request_id": "req001",
  "status": "processing",
  "message": "Generating video...",
  "progress": 65,
  "queue_position": 0,
  "start_time": "2024-11-27T14:30:52Z",
  "current_queue_size": 2
}
```

### Get Completed Result

**GET** `/{user_id}/{request_id}/result`

```bash
curl http://localhost:5000/user123/req001/result
```

**Response:**
```json
{
  "user_id": "user123",
  "request_id": "req001", 
  "status": "completed",
  "r2_output_path": "output-bucket/videos/user123/req001_20241127_143052.mp4",
  "public_url": "https://pub.r2.dev/videos/user123/req001_20241127_143052.mp4",
  "processing_time_minutes": 4.2,
  "created_time": "2024-11-27T14:30:00Z",
  "completed_time": "2024-11-27T14:34:12Z"
}
```

### Monitor Queue

**GET** `/queue`

```bash
curl http://localhost:5000/queue
```

### List All Requests

**GET** `/requests`

```bash
curl http://localhost:5000/requests
```

## 🔄 Processing Flow

1. **Request Submission**: Backend submits request with R2 asset paths
2. **Queue Position**: Request enters FIFO queue with position tracking
3. **Asset Download**: Server downloads image and audio from R2 
4. **Video Generation**: Executes `generate.py` with local asset paths
5. **Result Upload**: Uploads generated video to R2 output bucket
6. **Completion**: Returns R2 path and public URL to backend

## 📊 Status Types

- `queued`: Request waiting in queue
- `downloading`: Fetching assets from R2
- `processing`: Running video generation 
- `uploading`: Saving result to R2
- `completed`: All done, result available
- `failed_download`: Couldn't fetch R2 assets
- `failed_processing`: Video generation failed
- `failed_upload`: Couldn't save to R2
- `failed`: General failure

## 🧪 Testing

### Run Test Client

```bash
# Basic test
python test_client.py

# Custom server
python test_client.py --server http://gpu-server:5000

# Health check only
python test_client.py --health-only

# Monitor queue
python test_client.py --queue-info
```

### Manual Testing

```bash
# Submit test request
curl -X POST http://localhost:5000/test_user/test_req \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "Test video generation",
    "image_r2_path": "test-bucket/image.jpg", 
    "audio_r2_path": "test-bucket/audio.wav"
  }'

# Monitor status
watch -n 5 "curl -s http://localhost:5000/test_user/test_req/status | jq"

# Get result when completed
curl http://localhost:5000/test_user/test_req/result
```

## 🗂️ File Structure

```
Wan2.2/
├── app.py                     # Main Flask application
├── r2_client.py              # Cloudflare R2 integration 
├── queue_manager.py          # Sequential processing queue
├── test_client.py            # Test client for backend simulation
├── requirements_r2_api.txt   # Python dependencies
├── .env.example              # Environment configuration template
├── README_API.md             # This documentation
├── generate.py               # Original Wan generation script
├── workspace/                # Temporary processing files (created)
└── logs/                     # Application logs (created)
```

## ⚙️ Configuration Options

### Environment Variables

| Variable | Description | Default | Required |
|----------|-------------|---------|----------|
| `R2_ENDPOINT_URL` | R2 endpoint URL | - | ✅ |
| `R2_ACCESS_KEY_ID` | R2 access key | - | ✅ |
| `R2_SECRET_ACCESS_KEY` | R2 secret key | - | ✅ |
| `R2_OUTPUT_BUCKET` | Output bucket name | `output-bucket` | ✅ |
| `R2_REGION` | R2 region | `auto` | - |
| `R2_PUBLIC_DOMAIN` | Public domain for URLs | - | - |
| `WORKSPACE_DIR` | Local workspace | `workspace` | - |
| `CLEANUP_WORKSPACE` | Cleanup after processing | `true` | - |
| `WAN_CKPT_DIR` | Model checkpoint path | `./Wan2.2-S2V-14B/` | - |

### Command Line Options

```bash
python app.py --help

Options:
  --host HOST          Host to bind to (default: 127.0.0.1)
  --port PORT          Port to bind to (default: 5000)
  --debug              Enable debug mode
  --log-level LEVEL    Set logging level (DEBUG, INFO, WARNING, ERROR)
```

## 🚨 Error Handling

The API provides detailed error responses for common issues:

### Invalid Request Data
```json
{
  "error": "Invalid request data",
  "details": ["Missing required field: prompt"]
}
```

### R2 Access Issues
```json
{
  "error": "Processing failed: failed_download",
  "message": "Failed to download image: input-bucket/missing.jpg"
}
```

### Generation Failures
```json
{
  "error": "Processing failed: failed_processing", 
  "message": "Generation failed: CUDA out of memory"
}
```

## 🔧 Troubleshooting

### Server Won't Start
- Check R2 environment variables are set
- Verify model checkpoints exist
- Check port availability

### Requests Fail to Download
- Verify R2 credentials and permissions
- Check bucket names and file paths
- Test R2 connectivity

### Generation Failures
- Monitor GPU memory usage
- Check model checkpoint integrity
- Review generation logs

### Queue Issues
- Monitor queue status via `/queue` endpoint
- Check worker thread status
- Review server logs

## 📈 Monitoring

### Log Files
- Application logs: `wan_api.log`
- Error tracking: Check console output
- Queue status: Use `/queue` endpoint

### Health Monitoring
```bash
# Automated health checks
while true; do
  curl -f http://localhost:5000/health || echo "Server down"
  sleep 30
done
```

## 🔒 Security Considerations

- Use environment variables for R2 credentials
- Restrict API access with firewall rules
- Monitor request rates and implement limits
- Validate all input parameters
- Use HTTPS in production

## 📞 Support

For issues and questions:
1. Check the logs for detailed error messages
2. Verify R2 configuration and connectivity
3. Test with the provided test client
4. Monitor queue and system resources

This implementation provides a robust, production-ready API server for integrating Wan S2V processing into your backend architecture with full R2 cloud storage support.