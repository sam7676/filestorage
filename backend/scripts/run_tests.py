import argparse
import subprocess


def run(cmd):
    print(f"> {' '.join(cmd)}")
    subprocess.run(cmd, check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--coverage",
        action="store_true",
        help="Run tests with coverage enabled.",
    )
    args = parser.parse_args()

    if args.coverage:
        run(["uv", "run", "-m", "coverage", "run", "manage.py", "test", "api"])
        run(
            [
                "uv",
                "run",
                "-m",
                "coverage",
                "run",
                "--append",
                "-m",
                "pytest",
                "api/desktop/tests",
            ]
        )
    else:
        run(["uv", "run", "manage.py", "test", "api"])
        run(["uv", "run", "-m", "pytest", "api/desktop/tests"])


if __name__ == "__main__":
    main()
