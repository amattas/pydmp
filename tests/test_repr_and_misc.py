from pydmp.panel import DMPPanel
from pydmp.area import Area
from pydmp.zone import Zone
from pydmp.output import Output
from pydmp.status_parser import parse_s3_message
from pydmp.status_server import S3Message


def test_entity_reprs():
    panel = DMPPanel()
    # Panel repr before connect
    r = repr(panel)
    assert "disconnected" in r

    a = Area(panel, 1, "Main", state="D")
    z = Zone(panel, 2, "Front", state="N")
    o = Output(panel, 3, "Relay")

    assert "Area" in repr(a)
    assert "Zone" in repr(z)
    assert "Output" in repr(o)


def test_status_parser_unknown_category():
    msg = S3Message(account="00001", definition="Z?", type_code=None, fields=["Z?"], raw="")
    evt = parse_s3_message(msg)
    assert evt.category is None
    assert evt.code_enum is None
