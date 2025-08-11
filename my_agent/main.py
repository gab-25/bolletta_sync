import sys
from .agent import execute


if __name__ == "__main__":
    print("welcome to my-agent! press Ctrl+C to exit.")
    try:
        while True:
            request = input("user> ")
            response = execute(request)
            print(f"my-agent> {response}\n")
    except KeyboardInterrupt:
        print("\ngoodbye!")
        sys.exit(0)
