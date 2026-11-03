"""Generate a temporary-login hash without accepting passwords in command-line arguments."""

from getpass import getpass

from dispatcher.passwords import hash_password


def main() -> None:
    """Read a hidden terminal prompt and print only the salted hash for secret storage."""
    password = getpass("Test login password: ")
    if not password:
        raise SystemExit("Password cannot be empty")
    print(hash_password(password))


if __name__ == "__main__":
    main()
