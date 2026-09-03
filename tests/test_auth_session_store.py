import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main() -> None:
    with tempfile.TemporaryDirectory() as directory:
        previous = {key: os.environ.get(key) for key in ("DATABASE_URL", "SESSION_SIGNING_KEY")}
        os.environ["DATABASE_URL"] = f"sqlite:///{Path(directory) / 'auth.db'}"
        os.environ["SESSION_SIGNING_KEY"] = "test-session-signing-key-at-least-thirty-two-chars"
        try:
            from api.app import create_app

            client = create_app().test_client()
            os.environ["REGISTRATION_CODE"] = "invite"
            # Create an account through the public registration boundary once the
            # Render-side invitation secret is configured.
            register = client.post("/v1/auth/register", json={"username": "merchant-a", "password": "strong-password", "registration_code": "invite"})
            assert register.status_code == 201, register.get_data(as_text=True)
            login = client.post("/v1/auth/login", json={"username": "merchant-a", "password": "strong-password"})
            assert login.status_code == 200, login.get_data(as_text=True)
            token = login.json["access_token"]
            headers = {"Authorization": f"Bearer {token}"}
            assert client.get("/v1/auth/me", headers=headers).json["username"] == "merchant-a"
            assert client.post("/v1/auth/logout", headers=headers).status_code == 204
            assert client.get("/v1/auth/me", headers=headers).status_code == 401
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    print("Authentication session tests passed")


if __name__ == "__main__":
    main()
