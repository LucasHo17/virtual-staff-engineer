import argparse

from virtual_staff_engineer.ingestion import ingest_playbook


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Ingest a versioned Markdown engineering playbook."
    )
    parser.add_argument("path", help="Path to a Markdown playbook.")
    parser.add_argument(
        "--category",
        default="general",
        help="Playbook category stored with the document.",
    )
    return parser.parse_args()


if __name__ == "__main__":
    arguments = parse_arguments()
    ingest_playbook(arguments.path, category=arguments.category)
