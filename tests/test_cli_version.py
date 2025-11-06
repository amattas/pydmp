from click.testing import CliRunner

import pydmp.cli as cli
from pydmp import __version__


def test_cli_version_short_flag():
    r = CliRunner().invoke(cli.cli, ["-v"])  # short version flag
    assert r.exit_code == 0
    assert __version__ in r.output
