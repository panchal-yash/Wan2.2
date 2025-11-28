# Copyright 2024 R2 Integration for Wan S2V Processing
import os
import logging
from pathlib import Path
from typing import Optional, Tuple
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from botocore.config import Config

logger = logging.getLogger(__name__)


class R2Client:
    """Cloudflare R2 client for uploading and downloading assets"""
    
    def __init__(self, 
                 endpoint_url: str,
                 access_key_id: str, 
                 secret_access_key: str,
                 region_name: str = 'auto',
                 public_domain: Optional[str] = None):
        """
        Initialize R2 client with credentials
        
        Args:
            endpoint_url: R2 endpoint URL (e.g., https://account-id.r2.cloudflarestorage.com)
            access_key_id: R2 access key ID
            secret_access_key: R2 secret access key
            region_name: Region (usually 'auto' for R2)
            public_domain: Public domain for generating URLs (e.g., https://pub.r2.dev)
        """
        self.endpoint_url = endpoint_url
        self.public_domain = public_domain
        
        # Configure boto3 for R2
        config = Config(
            region_name=region_name,
            retries={
                'max_attempts': 3,
                'mode': 'adaptive'
            },
            max_pool_connections=50
        )
        
        try:
            self.s3_client = boto3.client(
                's3',
                endpoint_url=endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                config=config
            )
            logger.info("R2 client initialized successfully")
        except Exception as e:
            logger.error(f"Failed to initialize R2 client: {str(e)}")
            raise
    
    def parse_r2_path(self, r2_path: str) -> Tuple[str, str]:
        """
        Parse R2 path format: r2://bucket-name/path/to/file
        
        Args:
            r2_path: R2 path string
            
        Returns:
            Tuple of (bucket_name, object_key)
        """
        if not r2_path.startswith('r2://'):
            # If it's already a bucket/key format, try to parse it
            if '/' in r2_path:
                parts = r2_path.split('/', 1)
                return parts[0], parts[1]
            else:
                raise ValueError(f"Invalid R2 path format: {r2_path}")
        
        parsed = urlparse(r2_path)
        bucket_name = parsed.netloc
        object_key = parsed.path.lstrip('/')
        
        if not bucket_name or not object_key:
            raise ValueError(f"Invalid R2 path format: {r2_path}")
        
        return bucket_name, object_key
    
    def download_file(self, r2_path: str, local_file_path: str) -> bool:
        """
        Download a file from R2 to local filesystem
        
        Args:
            r2_path: R2 path (r2://bucket/path/file or bucket/path/file)
            local_file_path: Local file path to save to
            
        Returns:
            True if successful, False otherwise
        """
        try:
            bucket_name, object_key = self.parse_r2_path(r2_path)
            
            # Create local directory if it doesn't exist
            os.makedirs(os.path.dirname(local_file_path), exist_ok=True)
            
            logger.info(f"Downloading {bucket_name}/{object_key} to {local_file_path}")
            
            self.s3_client.download_file(bucket_name, object_key, local_file_path)
            
            # Verify file was downloaded
            if os.path.exists(local_file_path) and os.path.getsize(local_file_path) > 0:
                logger.info(f"Successfully downloaded {r2_path}")
                return True
            else:
                logger.error(f"Download failed - file is empty or doesn't exist: {local_file_path}")
                return False
                
        except ClientError as e:
            error_code = e.response['Error']['Code']
            if error_code == 'NoSuchKey':
                logger.error(f"File not found in R2: {r2_path}")
            elif error_code == 'NoSuchBucket':
                logger.error(f"Bucket not found in path: {r2_path}")
            else:
                logger.error(f"R2 client error downloading {r2_path}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error downloading {r2_path}: {str(e)}")
            return False
    
    def upload_file(self, local_file_path: str, r2_path: str, 
                   content_type: Optional[str] = None) -> bool:
        """
        Upload a file from local filesystem to R2
        
        Args:
            local_file_path: Local file path to upload
            r2_path: R2 destination path (r2://bucket/path/file or bucket/path/file)
            content_type: Optional content type (auto-detected if None)
            
        Returns:
            True if successful, False otherwise
        """
        try:
            if not os.path.exists(local_file_path):
                logger.error(f"Local file doesn't exist: {local_file_path}")
                return False
            
            bucket_name, object_key = self.parse_r2_path(r2_path)
            
            # Auto-detect content type if not provided
            if content_type is None:
                file_ext = Path(local_file_path).suffix.lower()
                content_type_map = {
                    '.mp4': 'video/mp4',
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.wav': 'audio/wav',
                    '.mp3': 'audio/mpeg'
                }
                content_type = content_type_map.get(file_ext, 'application/octet-stream')
            
            logger.info(f"Uploading {local_file_path} to {bucket_name}/{object_key}")
            
            extra_args = {'ContentType': content_type}
            self.s3_client.upload_file(local_file_path, bucket_name, object_key, 
                                     ExtraArgs=extra_args)
            
            logger.info(f"Successfully uploaded {r2_path}")
            return True
            
        except ClientError as e:
            logger.error(f"R2 client error uploading {local_file_path}: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error uploading {local_file_path}: {str(e)}")
            return False
    
    def generate_public_url(self, r2_path: str) -> Optional[str]:
        """
        Generate a public URL for an R2 object (if public domain is configured)
        
        Args:
            r2_path: R2 path (r2://bucket/path/file or bucket/path/file)
            
        Returns:
            Public URL string or None if not configured
        """
        if not self.public_domain:
            return None
        
        try:
            try:
                bucket_name, object_key = self.parse_r2_path(r2_path)
                # Remove bucket from path for public URL
                public_url = f"{self.public_domain.rstrip('/')}/{object_key}"
                return public_url
            except ValueError:
                # If parsing fails, bucket_name will be unbound
                logger.error(f"Failed to parse R2 path: {r2_path}")
                return None
        except Exception as e:
            logger.error(f"Error generating public URL for {r2_path}: {str(e)}")
            return None
    
    def file_exists(self, r2_path: str) -> bool:
        """
        Check if a file exists in R2
        
        Args:
            r2_path: R2 path (r2://bucket/path/file or bucket/path/file)
            
        Returns:
            True if file exists, False otherwise
        """
        try:
            bucket_name, object_key = self.parse_r2_path(r2_path)
            self.s3_client.head_object(Bucket=bucket_name, Key=object_key)
            return True
        except ClientError as e:
            if e.response['Error']['Code'] == '404':
                return False
            else:
                logger.error(f"Error checking if file exists {r2_path}: {str(e)}")
                return False
        except Exception as e:
            logger.error(f"Unexpected error checking file existence {r2_path}: {str(e)}")
            return False


def create_r2_client_from_env() -> R2Client:
    """
    Create R2 client from environment variables
    
    Required environment variables:
    - R2_ENDPOINT_URL
    - R2_ACCESS_KEY_ID  
    - R2_SECRET_ACCESS_KEY
    
    Optional:
    - R2_REGION (default: 'auto')
    - R2_PUBLIC_DOMAIN
    
    Returns:
        Configured R2Client instance
        
    Raises:
        ValueError: If required environment variables are missing
    """
    endpoint_url = os.getenv('R2_ENDPOINT_URL')
    access_key_id = os.getenv('R2_ACCESS_KEY_ID')
    secret_access_key = os.getenv('R2_SECRET_ACCESS_KEY')
    region_name = os.getenv('R2_REGION', 'auto')
    public_domain = os.getenv('R2_PUBLIC_DOMAIN')
    
    if not endpoint_url or not access_key_id or not secret_access_key:
        raise ValueError(
            "Missing required R2 environment variables. "
            "Please set R2_ENDPOINT_URL, R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY"
        )
    
    return R2Client(
        endpoint_url=endpoint_url,
        access_key_id=access_key_id,
        secret_access_key=secret_access_key,
        region_name=region_name,
        public_domain=public_domain
    )