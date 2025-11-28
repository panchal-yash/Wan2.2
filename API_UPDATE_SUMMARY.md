# Wan S2V API Update Summary

This document summarizes the changes made to implement the new `{user_id}/{video_id}/{segment_id}/` bucket structure.

## New R2 Bucket Structure

The R2 bucket now uses a simple 3-level hierarchy:

```
dolphintest/
├── user123/
│   ├── video001/
│   │   └── segment001/
│   │       ├── image.jpg     # Input image
│   │       ├── audio.wav     # Input audio  
│   │       ├── prompt.txt    # Input prompt
│   │       └── output.mp4    # Generated video
│   └── video002/
│       ├── segment001/
│       └── segment002/
└── user456/
    └── video001/
        └── segment001/
```

## API Changes

### Updated Endpoints

1. **Submit Request**: `POST /{user_id}/{video_id}/{segment_id}`
2. **Get Status**: `GET /{user_id}/{video_id}/{segment_id}/status`
3. **Get Result**: `GET /{user_id}/{video_id}/{segment_id}/result`

### New Request Payload

The request payload is now much simpler:

```json
{
  "bucket_name": "dolphintest",
  "size": "832*480", 
  "sample_guide_scale": 4.0,
  "sample_steps": 20,
  "ckpt_dir": "./Wan2.2-S2V-14B/"
}
```

**Note**: The `prompt`, `image_r2_path`, and `audio_r2_path` fields are no longer needed in the payload since the API automatically constructs the R2 paths based on the URL parameters.

## File Structure Requirements

For each segment, the R2 bucket must contain exactly these 3 input files:

- `{user_id}/{video_id}/{segment_id}/image.jpg` - Input image
- `{user_id}/{video_id}/{segment_id}/audio.wav` - Input audio
- `{user_id}/{video_id}/{segment_id}/prompt.txt` - Text prompt

After processing, the output will be saved to:

- `{user_id}/{video_id}/{segment_id}/output.mp4` - Generated video

## Code Changes Made

### 1. Updated `queue_manager.py`
- Modified `ProcessingRequest` dataclass to use `user_id`, `video_id`, `segment_id` instead of `request_id`
- Added properties for automatic R2 path construction:
  - `r2_image_path`
  - `r2_audio_path` 
  - `r2_prompt_path`
  - `r2_output_path`
- Updated workspace management to handle the new 3-level structure
- Added prompt.txt file handling in the download process
- Modified generation process to read prompt from downloaded prompt.txt file

### 2. Updated `app.py`
- Changed API endpoints to accept 3 URL parameters: `user_id`, `video_id`, `segment_id`
- Simplified request validation (no longer validates R2 paths or prompts)
- Updated queue manager initialization (removed output bucket dependency)
- Modified all endpoint responses to use the new URL structure

### 3. Updated `.env.example`
- Replaced `R2_OUTPUT_BUCKET` with `DEFAULT_BUCKET_NAME`
- Updated configuration comments to reflect new structure

### 4. Created `test_new_api.py`
- New test script demonstrating the updated API usage
- Shows how to submit requests with the new structure
- Includes examples for all endpoints

## Benefits of New Structure

1. **Simplicity**: Clean 3-level hierarchy that's easy to understand
2. **Scalability**: Natural organization for users with multiple videos and segments  
3. **Self-Contained**: Each segment folder contains all related files
4. **Atomic Operations**: Easy to manage individual segments
5. **Clean URLs**: Intuitive API endpoints that match the bucket structure

## Migration Notes

- Existing data in the old bucket structure will need to be reorganized
- API clients will need to update their integration to use the new endpoint format
- The new structure requires all 3 input files (image.jpg, audio.wav, prompt.txt) to be present before processing

## Example Usage

```python
# Submit a processing request
response = requests.post(
    "http://localhost:5000/user123/video001/segment001",
    json={
        "bucket_name": "dolphintest",
        "size": "832*480",
        "sample_guide_scale": 4.0,
        "sample_steps": 20
    }
)

# Check status
status = requests.get(
    "http://localhost:5000/user123/video001/segment001/status"
)

# Get result when completed
result = requests.get(
    "http://localhost:5000/user123/video001/segment001/result"
)
```

The system will automatically:
- Download `dolphintest/user123/video001/segment001/image.jpg`
- Download `dolphintest/user123/video001/segment001/audio.wav`
- Download `dolphintest/user123/video001/segment001/prompt.txt`
- Process the video
- Upload result to `dolphintest/user123/video001/segment001/output.mp4`