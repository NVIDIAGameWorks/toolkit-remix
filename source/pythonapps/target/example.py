import argparse
import importlib
import os, sys
import glob

if __name__ == "__main__":
    # Discover all examples in examples folder:
    examples = []
    app_path = os.path.dirname(os.path.abspath(__file__))
    for file in glob.glob(os.path.join(app_path, "examples/*.py")):
        examples.append(os.path.splitext(os.path.basename(file))[0])

    # Select example to run
    parser = argparse.ArgumentParser()
    parser.prog = "Python App Examples"
    parser.description = ""
    parser.add_argument(
        "example",
        choices=examples,
        const=examples[0],
        nargs="?",
        default=examples[0],
        help="Example to run. (default: %(default)s)",
    )
    options, argv_left = parser.parse_known_args()
    sys.argv = [sys.argv[0]] + argv_left  # Keep first arg (executable name)

    # Run an example!
    mod = importlib.import_module(f"examples.{options.example}")
    sys.exit(mod.run())
