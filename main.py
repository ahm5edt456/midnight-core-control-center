#!/usr/bin/python3

import sys

from midnight.application import MidnightApplication


def main():
    app = MidnightApplication()
    return app.run(sys.argv)


if __name__ == "__main__":
    sys.exit(main())
