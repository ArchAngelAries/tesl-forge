"""Entry point of the installed "TESL Forge.exe": the app in its own window. (The command line is `tesl` in the zip
version; a windowed exe has no console to print to.)"""
import sys

from tesl_suite.window import main

if __name__ == "__main__":
    sys.exit(main())
