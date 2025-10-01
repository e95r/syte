from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import os

SECRET_KEY = os.getenv("SECRET_KEY", "dev-secret")
_signer = URLSafeTimedSerializer(SECRET_KEY, salt="email-verify")

def make_email_token(user_id: int, email: str) -> str:
    return _signer.dumps({"uid": user_id, "email": email})

def load_email_token(token: str, max_age: int = 60 * 60 * 24) -> dict | None:
    try:
        return _signer.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None
