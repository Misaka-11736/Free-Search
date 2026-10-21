from multiprocessing import freeze_support
from free_search.__main__ import main

if __name__ == "__main__":
    freeze_support()
    raise SystemExit(main())
