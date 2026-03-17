import os
from dataclasses import dataclass


@dataclass
class IBMCloudObjectStorage:
    endpoint_url: str
    api_key: str
    resource_instance_id: str
    access_key_id: str
    secret_access_key: str
    bucket: str

    @classmethod
    def from_env(cls):
        return cls(
            endpoint_url=(os.getenv("IBM_COS_ENDPOINT") or "").strip(),
            api_key=(os.getenv("IBM_COS_API_KEY") or "").strip(),
            resource_instance_id=(os.getenv("IBM_COS_RESOURCE_INSTANCE_ID") or "").strip(),
            access_key_id=(os.getenv("IBM_COS_ACCESS_KEY_ID") or "").strip(),
            secret_access_key=(os.getenv("IBM_COS_SECRET_ACCESS_KEY") or "").strip(),
            bucket=(os.getenv("IBM_COS_BUCKET") or "").strip(),
        )

    def is_configured(self) -> bool:
        return all([
            self.endpoint_url,
            self.api_key,
            self.resource_instance_id,
            self.access_key_id,
            self.secret_access_key,
            self.bucket,
        ])

    def status(self) -> str:
        if not self.is_configured():
            return "IBM Cloud Object Storage: ❌ не настроен (проверь IBM_COS_* переменные)"
        return f"IBM Cloud Object Storage: ✅ готов ({self.bucket})"

    def client(self):
        try:
            import boto3  # type: ignore
            from ibm_botocore.client import Config  # type: ignore
        except Exception as e:
            raise RuntimeError(
                f"IBM COS SDK не установлен: {e}. Установи: pip install boto3 ibm-cos-sdk-core"
            ) from e

        return boto3.client(
            "s3",
            ibm_api_key_id=self.api_key,
            ibm_service_instance_id=self.resource_instance_id,
            aws_access_key_id=self.access_key_id,
            aws_secret_access_key=self.secret_access_key,
            config=Config(signature_version=os.getenv("IBM_COS_SIGNATURE_VERSION", "oauth").strip()),
            endpoint_url=self.endpoint_url,
        )
