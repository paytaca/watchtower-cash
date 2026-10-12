import json

from django.core.management.base import BaseCommand, CommandError

from cts.utils import build_authchain


class Command(BaseCommand):
    help = (
        "Reconstruct the authchain [authbase, ..., authhead] from the node. "
        "Node-only: performs no database reads or writes."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--authhead",
            type=str,
            required=True,
            help="The authhead txid (current unspent identity output).",
        )
        parser.add_argument(
            "--authbase",
            type=str,
            required=True,
            help="The authbase txid (the authchain's index-0 base).",
        )
        parser.add_argument(
            "--max-depth",
            type=int,
            default=1500,
            help="Maximum number of links to walk before giving up (default: 1500).",
        )

    def handle(self, *args, **options):
        try:
            chain = build_authchain(
                options["authhead"],
                options["authbase"],
                max_depth=options["max_depth"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(json.dumps(chain))
