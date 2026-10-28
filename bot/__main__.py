from . import premium_setup

premium_setup.install()

from .app import main  # noqa: E402

if __name__ == "__main__":
    main()
